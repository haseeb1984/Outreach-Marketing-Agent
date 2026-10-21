"""Persistence for verified inbound replies; provider payloads are not logged."""
from __future__ import annotations
from typing import Any
from uuid import UUID

class ConversationStore:
    def __init__(self,pool: Any)->None: self._pool=pool

    async def ingest_reply(self,*,workspace_id: str,prospect_id: UUID,provider: str,event_id: str,
                           message_id: str,in_reply_to: str|None,channel: str,body: str,occurred_at: Any)->dict[str,Any]:
        async with self._pool.acquire() as c:
            async with c.transaction():
                prospect=await c.fetchrow("""SELECT id FROM crm_prospects WHERE id=$1 AND workspace_id=$2
                    AND archived_at IS NULL FOR UPDATE""",prospect_id,workspace_id)
                if prospect is None: raise LookupError("prospect_not_found")
                row=await c.fetchrow("""INSERT INTO outreach_conversation_messages
                    (workspace_id,prospect_id,provider,provider_event_id,provider_message_id,
                     in_reply_to_provider_message_id,channel,direction,body,occurred_at)
                    VALUES($1,$2,$3,$4,$5,$6,$7,'inbound',$8,$9)
                    ON CONFLICT(provider,provider_event_id) DO NOTHING
                    RETURNING id,workspace_id,prospect_id,provider,provider_event_id,provider_message_id,
                              in_reply_to_provider_message_id,channel,direction,body,occurred_at,received_at""",
                    workspace_id,prospect_id,provider,event_id,message_id,in_reply_to,channel,body,occurred_at)
                if row is None:
                    return {"duplicate":True,"event_id":event_id}
                await c.execute("""UPDATE crm_prospects SET stage='replied',updated_at=now()
                    WHERE id=$1 AND workspace_id=$2 AND stage NOT IN ('do_not_contact','disqualified')""",
                    prospect_id,workspace_id)
                result=dict(row)
                for k in ("id","prospect_id"): result[k]=str(result[k])
                return {"duplicate":False,"message":result}

    async def list_messages(self,*,workspace_id: str,prospect_id: UUID,limit: int=50,offset: int=0)->list[dict[str,Any]]:
        if not 1<=limit<=100 or not 0<=offset<=100000: raise ValueError("pagination_out_of_range")
        async with self._pool.acquire() as c:
            rows=await c.fetch("""SELECT id,workspace_id,prospect_id,provider,provider_event_id,
                provider_message_id,in_reply_to_provider_message_id,channel,direction,body,occurred_at,received_at
                FROM outreach_conversation_messages WHERE workspace_id=$1 AND prospect_id=$2
                ORDER BY occurred_at DESC,id DESC LIMIT $3 OFFSET $4""",workspace_id,prospect_id,limit,offset)
        result=[]
        for row in rows:
            item=dict(row); item["id"]=str(item["id"]); item["prospect_id"]=str(item["prospect_id"]); result.append(item)
        return result
