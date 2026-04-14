from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import CurrentUser, DbSession
from app.models import Category, CategoryGroup
from app.schemas.category import (
    CategoryCreate,
    CategoryGroupCreate,
    CategoryGroupResponse,
    CategoryGroupUpdate,
    CategoryResponse,
    CategoryUpdate,
)

router = APIRouter(prefix="/api", tags=["categories"])


async def _owned_group(db, user_id: int, group_id: int) -> CategoryGroup:
    group = await db.get(CategoryGroup, group_id)
    if group is None or group.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category group not found"
        )
    return group


async def _owned_category(db, user_id: int, category_id: int) -> Category:
    category = await db.get(Category, category_id)
    if category is None or category.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return category


@router.get("/category-groups", response_model=list[CategoryGroupResponse])
async def list_groups(
    db: DbSession, current_user: CurrentUser
) -> list[CategoryGroupResponse]:
    groups = (
        (
            await db.execute(
                select(CategoryGroup)
                .where(CategoryGroup.user_id == current_user.id)
                .order_by(CategoryGroup.sort_order, CategoryGroup.id)
            )
        )
        .scalars()
        .all()
    )
    cats_by_group: dict[int, list[CategoryResponse]] = {}
    cats = (
        (
            await db.execute(
                select(Category)
                .where(Category.user_id == current_user.id)
                .order_by(Category.sort_order, Category.id)
            )
        )
        .scalars()
        .all()
    )
    for c in cats:
        cats_by_group.setdefault(c.group_id, []).append(CategoryResponse.model_validate(c))
    return [
        CategoryGroupResponse(
            id=g.id,
            name=g.name,
            sort_order=g.sort_order,
            categories=cats_by_group.get(g.id, []),
        )
        for g in groups
    ]


@router.post(
    "/category-groups",
    response_model=CategoryGroupResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_group(
    payload: CategoryGroupCreate, db: DbSession, current_user: CurrentUser
) -> CategoryGroupResponse:
    group = CategoryGroup(
        user_id=current_user.id, name=payload.name, sort_order=payload.sort_order
    )
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return CategoryGroupResponse(
        id=group.id, name=group.name, sort_order=group.sort_order, categories=[]
    )


@router.patch("/category-groups/{group_id}", response_model=CategoryGroupResponse)
async def update_group(
    group_id: int,
    payload: CategoryGroupUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> CategoryGroupResponse:
    group = await _owned_group(db, current_user.id, group_id)
    if payload.name is not None:
        group.name = payload.name
    if payload.sort_order is not None:
        group.sort_order = payload.sort_order
    await db.commit()
    await db.refresh(group)
    return CategoryGroupResponse(
        id=group.id, name=group.name, sort_order=group.sort_order, categories=[]
    )


@router.delete("/category-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(group_id: int, db: DbSession, current_user: CurrentUser) -> None:
    group = await _owned_group(db, current_user.id, group_id)
    await db.delete(group)
    await db.commit()


@router.post(
    "/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED
)
async def create_category(
    payload: CategoryCreate, db: DbSession, current_user: CurrentUser
) -> CategoryResponse:
    # Ensure the target group belongs to the current user.
    await _owned_group(db, current_user.id, payload.group_id)
    category = Category(
        user_id=current_user.id,
        group_id=payload.group_id,
        name=payload.name,
        sort_order=payload.sort_order,
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return CategoryResponse.model_validate(category)


@router.patch("/categories/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: int,
    payload: CategoryUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> CategoryResponse:
    category = await _owned_category(db, current_user.id, category_id)
    if payload.group_id is not None:
        await _owned_group(db, current_user.id, payload.group_id)
        category.group_id = payload.group_id
    if payload.name is not None:
        category.name = payload.name
    if payload.sort_order is not None:
        category.sort_order = payload.sort_order
    await db.commit()
    await db.refresh(category)
    return CategoryResponse.model_validate(category)


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: int, db: DbSession, current_user: CurrentUser
) -> None:
    category = await _owned_category(db, current_user.id, category_id)
    await db.delete(category)
    await db.commit()
