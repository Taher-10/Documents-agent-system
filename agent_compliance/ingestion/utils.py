from __future__ import annotations

import uuid


_QHSE_UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "agent_compliance.qhse_sections")


def stable_uuid(doc_id: str, section_id: str) -> str:
    seed = f"{doc_id}:{section_id}"
    return str(uuid.uuid5(_QHSE_UUID_NAMESPACE, seed))
