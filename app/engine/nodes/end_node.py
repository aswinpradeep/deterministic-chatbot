"""`end` node — terminate the conversation.

YAML shape:
    - id: satisfied
      type: end
      outcome: self_served
      prompt:
        text: "I hope this helps. Please let me know if you need any further assistance."
"""

from __future__ import annotations

from typing import Any, Callable

from app.engine.activity import Activity
from app.engine.nodes.base import NodeHandler
from app.engine.state import ConversationState, FlowStatus
from app.engine.template import render


class EndNode(NodeHandler):
    node_type = "end"

    def build(self, cfg: dict[str, Any]) -> Callable[[ConversationState], dict]:
        self._validate(cfg)

        outcome = cfg.get("outcome", "ended")
        prompt = cfg.get("prompt", {})
        action_button_raw: dict | None = cfg.get("action_button")

        def run(state: ConversationState) -> dict:
            activities: list[dict] = []
            ctx = {
                "collected": state.collected,
                "counters": state.counters,
                "user_id_hash": state.user_id_hash,
                "channel": state.channel,
            }
            # `pending_activities` is reset to [] at the start of every user turn
            # (see app/api/routes.py:_build_state_update). If it already has entries
            # here, this end node was reached by auto-chaining from a prior node in
            # the SAME turn (e.g. a plain `message` node with `next: satisfied`) —
            # merge into that node's bubble instead of opening a visually separate
            # second response box. If it's empty, this end node is the sole output
            # of the turn (e.g. resumed after a quick-reply interrupt) and renders
            # its own bubble as before.
            base_activities = list(state.pending_activities)
            merge_target = base_activities[-1] if base_activities else None

            if prompt:
                text = render(prompt.get("text", ""), ctx)
                if text:
                    if merge_target and merge_target.get("type") == "markdown":
                        prior_text = merge_target.get("content", "").rstrip()
                        merge_target["content"] = f"{prior_text}\n\n{text}"
                    else:
                        activities.append(
                            Activity.markdown(text).model_dump(exclude_none=True)
                        )
            if action_button_raw:
                btn_label = render(action_button_raw.get("label", ""), ctx)
                btn_url   = render(action_button_raw.get("url", ""), ctx)
                if btn_label and btn_url:
                    activities.append(
                        Activity.action_button(label=btn_label, url=btn_url).model_dump(
                            exclude_none=True
                        )
                    )
            activities.append(
                Activity.end(outcome=outcome).model_dump(exclude_none=True)
            )

            status = (
                FlowStatus.SATISFIED if outcome == "self_served"
                else FlowStatus.TICKET_RAISED if outcome == "ticket_raised"
                else FlowStatus.ENDED
            )

            return {
                "pending_activities": base_activities + activities,
                "current_node": cfg["id"],
                "status": status,
            }

        return run

    def next_node(self, cfg: dict[str, Any]) -> str | None:
        return None  # terminal — wired to END in compiler
