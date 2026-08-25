"""A thread is named by the model, not by its first sentence.

A saved conversation took its title from the question that opened it, so a list
of threads read as a column of sentences all starting "Tell me about" and
"Have we ever", which is the part that says nothing. A name says what the
thread is about.

Naming is still a model call and so it is still a registered capability, with
an owner, a data-class ceiling and a kill switch, like every other. It carries
no gate: it states nothing about the record, cites nothing, and anybody can
rename the thread, so there is nothing a measurement would protect.

Revision ID: 0020
Revises: 0019
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO capability (
            id, created_at, updated_at, code, name, module, purpose, owner_id,
            max_data_class, tier_ceiling, human_requirement, confirming_role,
            state, disabled_for_types, metric_name, gate_expression,
            gate_threshold, gate_enforced, prompt_reference, tools_allowed
        )
        SELECT
            gen_random_uuid(), now(), now(),
            'conversation_title', 'Conversation title', 'M10',
            'Naming a saved thread. Anyone may rename it, and nothing depends on the name.',
            (SELECT owner_id FROM capability WHERE code = 'clause_retrieval_answer'),
            'confidential', 'tier_4',
            'Naming a saved thread. Anyone may rename it, and nothing depends on the name.',
            'legal_ops', 'enabled', '[]'::jsonb,
            'Not measured', 'no gate, the output makes no claim about the record',
            NULL, false, 'prompts/conversation_title@v1', '[]'::jsonb
        WHERE NOT EXISTS (SELECT 1 FROM capability WHERE code = 'conversation_title')
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM capability WHERE code = 'conversation_title'")
