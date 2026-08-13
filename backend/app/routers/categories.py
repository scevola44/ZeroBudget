from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, update

from app.deps import CurrentUser, DbSession, owned_scope
from app.models import Category, CategoryGroup, Scope, Transaction
from app.schemas.category import (
    CategoryCreate,
    CategoryGroupCreate,
    CategoryGroupResponse,
    CategoryGroupUpdate,
    CategoryResponse,
    CategoryUpdate,
    YnabImportRequest,
    YnabImportResponse,
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
            scope_id=g.scope_id,
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
    await owned_scope(db, current_user.id, payload.scope_id)
    group = CategoryGroup(
        user_id=current_user.id,
        name=payload.name,
        sort_order=payload.sort_order,
        scope_id=payload.scope_id,
    )
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return CategoryGroupResponse(
        id=group.id,
        name=group.name,
        sort_order=group.sort_order,
        scope_id=group.scope_id,
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
    if payload.scope_id is not None and payload.scope_id != group.scope_id:
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
        await owned_scope(db, current_user.id, payload.scope_id)
        group.scope_id = payload.scope_id
    await db.commit()
    await db.refresh(group)
    return CategoryGroupResponse(
        id=group.id,
        name=group.name,
        sort_order=group.sort_order,
        scope_id=group.scope_id,
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
    category_id: int,
    db: DbSession,
    current_user: CurrentUser,
    reassign_to: int | None = Query(
        default=None,
        description="Move this category's transactions here before deleting it.",
    ),
) -> None:
    """Delete a category, optionally rehoming its transactions first.

    Without ``reassign_to`` the transactions keep a NULL category (the FK is
    ON DELETE SET NULL) and read as uncategorized. Either way the category's
    monthly assignments cascade away with it, so the money it was holding
    returns to Ready to Assign in every month it was assigned.
    """
    category = await _owned_category(db, current_user.id, category_id)

    if reassign_to is not None:
        if reassign_to == category_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cannot reassign a category's transactions to itself.",
            )
        target = await _owned_category(db, current_user.id, reassign_to)
        source_group = await _owned_group(db, current_user.id, category.group_id)
        target_group = await _owned_group(db, current_user.id, target.group_id)
        if source_group.scope_id != target_group.scope_id:
            # Moving them would strand transactions in a category whose scope
            # disagrees with their account — exactly what the transaction
            # router's scope guard exists to prevent.
            source_scope = await db.get(Scope, source_group.scope_id)
            target_scope = await db.get(Scope, target_group.scope_id)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Cannot move transactions from a {source_scope.name} category "
                    f"to a {target_scope.name} one."
                ),
            )
        await db.execute(
            update(Transaction)
            .where(
                Transaction.user_id == current_user.id,
                Transaction.category_id == category_id,
            )
            .values(category_id=reassign_to)
        )

    await db.delete(category)
    await db.commit()


@router.post("/categories/import-ynab", response_model=YnabImportResponse)
async def import_from_ynab(
    payload: YnabImportRequest, db: DbSession, current_user: CurrentUser
) -> YnabImportResponse:
    existing_groups = (
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
    existing_cats = (
        (
            await db.execute(
                select(Category).where(Category.user_id == current_user.id)
            )
        )
        .scalars()
        .all()
    )

    groups_by_name: dict[str, CategoryGroup] = {g.name: g for g in existing_groups}
    group_id_to_name: dict[int, str] = {g.id: g.name for g in existing_groups}
    existing_cat_keys: set[tuple[int, str]] = {
        (c.group_id, c.name) for c in existing_cats
    }
    # Track how many categories already exist per group name for sort_order.
    cats_in_group: dict[str, int] = {}
    for c in existing_cats:
        name = group_id_to_name.get(c.group_id)
        if name is not None:
            cats_in_group[name] = cats_in_group.get(name, 0) + 1

    next_group_order = max((g.sort_order for g in existing_groups), default=-1) + 1
    unique_groups: list[str] = []
    seen: set[str] = set()
    for row in payload.rows:
        if row.group not in seen:
            unique_groups.append(row.group)
            seen.add(row.group)

    groups_created = 0
    for i, group_name in enumerate(unique_groups):
        if group_name not in groups_by_name:
            new_group = CategoryGroup(
                user_id=current_user.id,
                name=group_name,
                sort_order=next_group_order + i,
            )
            db.add(new_group)
            groups_by_name[group_name] = new_group
            groups_created += 1

    await db.flush()

    categories_created = 0
    for row in payload.rows:
        group = groups_by_name[row.group]
        key = (group.id, row.category)
        if key not in existing_cat_keys:
            sort_order = cats_in_group.get(row.group, 0)
            new_cat = Category(
                user_id=current_user.id,
                group_id=group.id,
                name=row.category,
                sort_order=sort_order,
                goal_kind="monthly",
                goal_amount_cents=0,
            )
            db.add(new_cat)
            existing_cat_keys.add(key)
            cats_in_group[row.group] = sort_order + 1
            categories_created += 1

    await db.commit()
    return YnabImportResponse(
        groups_created=groups_created, categories_created=categories_created
    )
