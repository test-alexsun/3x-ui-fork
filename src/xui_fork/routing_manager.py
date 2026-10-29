"""Never overwrite user routing rules without a proven merge contract."""


def require_manual_review(existing: object, proposed: object) -> None:
    if existing != proposed:
        raise RuntimeError("routing changes require a tested merge adapter")
