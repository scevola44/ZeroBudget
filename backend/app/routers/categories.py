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
    _validate_goal_combo,
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
            scope=g.scope,
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
        user_id=current_user.id,
        name=payload.name,
        sort_order=payload.sort_order,
        scope=payload.scope,
    )
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return CategoryGroupResponse(
        id=group.id,
        name=group.name,
        sort_order=group.sort_order,
        scope=group.scope,
        categories=[],
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
    if payload.scope is not None and payload.scope != group.scope:
        # Changing scope on a group with categories would silently shift
        # assignments and balances between Ready-to-Assign pools. Restrict to
        # empty groups; the user can move categories elsewhere first.
        existing_cat = await db.scalar(
            select(Category.id).where(Category.group_id == group.id).limit(1)
        )
        if existing_cat is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot change scope on a group that contains categories.",
            )
        group.scope = payload.scope
    await db.commit()
    await db.refresh(group)
    return CategoryGroupResponse(
        id=group.id,
        name=group.name,
        sort_order=group.sort_order,
        scope=group.scope,
        categories=[],
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
        goal_kind=payload.goal_kind,
        goal_amount_cents=payload.goal_amount_cents,
        goal_target_month=payload.goal_target_month,
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

    # Goal updates: merge any explicitly-set goal fields with the persisted
    # row, then re-run the cross-field rule on the resulting triple.
    fields_set = payload.model_fields_set
    if fields_set & {"goal_kind", "goal_amount_cents", "goal_target_month"}:
        new_kind = payload.goal_kind if "goal_kind" in fields_set else category.goal_kind
        new_amount = (
            payload.goal_amount_cents
            if "goal_amount_cents" in fields_set
            else category.goal_amount_cents
        )
        new_target = (
            payload.goal_target_month
            if "goal_target_month" in fields_set
            else category.goal_target_month
        )
        try:
            _validate_goal_combo(new_kind, new_amount, new_target)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        category.goal_kind = new_kind
        category.goal_amount_cents = new_amount
        category.goal_target_month = new_target

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
