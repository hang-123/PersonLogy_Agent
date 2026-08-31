from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from personlogy.application.schema_management import SchemaChangeService
from personlogy.domain.schema import SchemaProposal

from app.modules.schema_management.schemas import (
    SchemaApprovalRequest,
    SchemaChangeResponse,
    SchemaProposalCreateRequest,
    SchemaProposalResponse,
)
from app.runtime import schema_service

router = APIRouter(prefix="/schema-proposals", tags=["schema-management"])


def _require_service() -> SchemaChangeService:
    if schema_service is None:
        raise HTTPException(status_code=503, detail="schema management is not configured")
    return schema_service


def _response(proposal: SchemaProposal) -> SchemaProposalResponse:
    return SchemaProposalResponse(
        id=proposal.id,
        namespace=proposal.namespace,
        base_version=proposal.base_version,
        target_version=proposal.target_version,
        definition=proposal.definition,
        changes=[
            SchemaChangeResponse(
                kind=change.kind.value,
                path=change.path,
                before=change.before,
                after=change.after,
            )
            for change in proposal.changes
        ],
        author=proposal.author,
        status=proposal.status.value,
        created_at=proposal.created_at,
        validated_at=proposal.validated_at,
        approved_by=proposal.approved_by,
        approved_at=proposal.approved_at,
        applied_at=proposal.applied_at,
        rolled_back_at=proposal.rolled_back_at,
    )


@router.post("", response_model=SchemaProposalResponse, status_code=status.HTTP_201_CREATED)
async def create_proposal(
    request: SchemaProposalCreateRequest,
) -> SchemaProposalResponse:
    proposal = await _require_service().propose(
        namespace=request.namespace,
        target_definition=request.target_definition,
        author=request.author,
    )
    return _response(proposal)


@router.get("/{proposal_id}", response_model=SchemaProposalResponse)
async def get_proposal(proposal_id: UUID) -> SchemaProposalResponse:
    proposal = await _require_service().get(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="schema proposal was not found")
    return _response(proposal)


@router.post("/{proposal_id}/validate", response_model=SchemaProposalResponse)
async def validate_proposal(proposal_id: UUID) -> SchemaProposalResponse:
    return _response(await _require_service().validate(proposal_id))


@router.post("/{proposal_id}/approve", response_model=SchemaProposalResponse)
async def approve_proposal(
    proposal_id: UUID, request: SchemaApprovalRequest
) -> SchemaProposalResponse:
    return _response(
        await _require_service().approve(proposal_id, approver=request.approver)
    )


@router.post("/{proposal_id}/execute", response_model=SchemaProposalResponse)
async def execute_proposal(proposal_id: UUID) -> SchemaProposalResponse:
    return _response(await _require_service().execute(proposal_id))


@router.post("/{proposal_id}/rollback", response_model=SchemaProposalResponse)
async def rollback_proposal(proposal_id: UUID) -> SchemaProposalResponse:
    return _response(await _require_service().rollback(proposal_id))


__all__ = ["router"]
