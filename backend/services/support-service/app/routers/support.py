"""Rute protejate (JWT) ale support-service.

Extern (prin Gateway) acestea devin:
  POST /api/support/tickets
  GET  /api/support/tickets
  GET  /api/support/tickets/{id}

Userul vede DOAR propriile tichete — identitatea vine din JWT.
"""

from fastapi import APIRouter, status

from app import service
from app.models import TicketCreate, TicketOut
from app.security import CurrentUserId

router = APIRouter(prefix="/tickets", tags=["support"])


@router.post("", response_model=TicketOut, response_model_by_alias=False, status_code=status.HTTP_201_CREATED)
async def create_ticket(payload: TicketCreate, user_id: str = CurrentUserId):
    return await service.create_ticket(user_id, payload)


@router.get("", response_model=list[TicketOut], response_model_by_alias=False)
async def list_my_tickets(user_id: str = CurrentUserId):
    return await service.list_tickets_for_user(user_id)


@router.get("/{ticket_id}", response_model=TicketOut, response_model_by_alias=False)
async def get_ticket(ticket_id: str, user_id: str = CurrentUserId):
    return await service.get_ticket_for_user(ticket_id, user_id)
