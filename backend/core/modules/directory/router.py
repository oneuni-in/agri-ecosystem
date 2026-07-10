"""Directory module routes. Endpoints land in later specs."""

from shared.security import SecureRouter

router = SecureRouter(prefix="/directory", tags=["directory"])


@router.get("/bad-demo-open", public=True)
async def bad_demo_open() -> dict[str, str]:
    """Deliberately undeclared public route - must turn the public-routes gate red."""
    return {"status": "exposed"}
