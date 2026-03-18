"""RAG search helpers for service and IAM mappings."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ServiceMapping, IAMMapping


async def search_service_mappings(
    aws_service: str,
    aws_resource_type: str,
    db: AsyncSession,
) -> list:
    """Find service mappings matching the given AWS service and resource type."""
    query = select(ServiceMapping).where(
        ServiceMapping.aws_service.ilike(f"%{aws_service}%"),
        ServiceMapping.aws_resource_type.ilike(f"%{aws_resource_type}%"),
    )
    result = await db.execute(query)
    return result.scalars().all()


async def lookup_iam_mapping(aws_action: str, db: AsyncSession):
    """Look up a single IAM mapping by exact AWS action."""
    result = await db.execute(
        select(IAMMapping).where(IAMMapping.aws_action == aws_action)
    )
    return result.scalar_one_or_none()
