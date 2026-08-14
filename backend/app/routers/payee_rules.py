from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import CurrentUser, DbSession
from app.models import Category, PayeeCategoryRule
from app.schemas.payee_rule import (
    PayeeCategoryRuleCreate,
    PayeeCategoryRuleResponse,
    PayeeCategoryRuleUpdate,
)

router = APIRouter(prefix="/api/payee-rules", tags=["payee-rules"])


async def _owned_rule(db: AsyncSession, user_id: int, rule_id: int) -> PayeeCategoryRule:
    rule = await db.get(PayeeCategoryRule, rule_id)
    if rule is None or rule.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return rule


async def _owned_category(db: AsyncSession, user_id: int, category_id: int) -> Category:
    category = await db.get(Category, category_id)
    if category is None or category.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid category")
    return category


@router.get("", response_model=list[PayeeCategoryRuleResponse])
async def list_payee_rules(db: DbSession, current_user: CurrentUser) -> list[PayeeCategoryRule]:
    result = await db.execute(
        select(PayeeCategoryRule)
        .where(PayeeCategoryRule.user_id == current_user.id)
        .order_by(PayeeCategoryRule.sort_order, PayeeCategoryRule.id)
    )
    return list(result.scalars().all())


@router.post("", response_model=PayeeCategoryRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_payee_rule(
    payload: PayeeCategoryRuleCreate, db: DbSession, current_user: CurrentUser
) -> PayeeCategoryRule:
    await _owned_category(db, current_user.id, payload.category_id)
    rule = PayeeCategoryRule(
        user_id=current_user.id,
        category_id=payload.category_id,
        contains_text=payload.contains_text.strip(),
        sort_order=payload.sort_order,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.patch("/{rule_id}", response_model=PayeeCategoryRuleResponse)
async def update_payee_rule(
    rule_id: int, payload: PayeeCategoryRuleUpdate, db: DbSession, current_user: CurrentUser
) -> PayeeCategoryRule:
    rule = await _owned_rule(db, current_user.id, rule_id)
    if payload.category_id is not None:
        await _owned_category(db, current_user.id, payload.category_id)
        rule.category_id = payload.category_id
    if payload.contains_text is not None:
        rule.contains_text = payload.contains_text.strip()
    if payload.sort_order is not None:
        rule.sort_order = payload.sort_order
    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payee_rule(rule_id: int, db: DbSession, current_user: CurrentUser) -> None:
    rule = await _owned_rule(db, current_user.id, rule_id)
    await db.delete(rule)
    await db.commit()
