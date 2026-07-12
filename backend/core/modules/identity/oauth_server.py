"""authlib AuthorizationServer wiring (D08.A/D/E) - protocol logic, no HTTP.

The async/sync bridge: authlib's framework-agnostic core is synchronous while
our DB layer is async, so the router PREFETCHES every row a request can need
(client, atomically-consumed code, token subject) into a RequestContext, then
runs authlib's validation - which from that point is pure CPU: parameter
checks, exact redirect matching, PKCE S256 comparison, RS256 signing. The
hooks below only read the context; none of them touches the database.

Everything protocol-shaped is authlib's (or joserfc's, its JOSE successor):
S256 comparison is authlib's compare function inside CodeChallenge, the JWT is
joserfc's jwt.encode. Nothing cryptographic is hand-rolled here - this module
only decides WHICH rows authlib gets to see.

Deviations from bare RFC 6749, all tightening (spec E + non-negotiables):
- code_challenge with method S256 is required at /authorize (authlib 1.7 only
  enforces PKCE at the token endpoint, so S256CodeChallenge adds the
  authorize-side check); "plain" does not exist here.
- state is required, not recommended - the router raises before issuing
  anything when it is missing.
- clients are public ("none" token-endpoint auth) and may use exactly
  response_type=code / grant_type=authorization_code or refresh_token. The
  refresh grant (D09) rides opaque rotating tokens: the router rotates them
  atomically BEFORE authlib runs (burn-on-attempt), authlib only confirms the
  prefetched result and the token generator attaches the new plaintext.
"""

import time
import uuid
from dataclasses import dataclass
from typing import Any

from authlib.oauth2.rfc6749 import (
    AuthorizationCodeMixin,
    AuthorizationServer,
    ClientMixin,
    InvalidRequestError,
    grants,
)
from authlib.oauth2.rfc6749.requests import BasicOAuth2Payload, OAuth2Request
from authlib.oauth2.rfc7636 import CodeChallenge
from joserfc import jwt
from starlette.responses import JSONResponse, Response

from modules.identity.models import OAuthClient, OAuthCode
from modules.identity.oauth_keys import get_signing_key
from modules.identity.oauth_limits import ACCESS_TOKEN_TTL_SECONDS
from modules.identity.oauth_service import TokenSubject, hash_code
from modules.identity.refresh_service import RefreshRotation
from settings import get_settings


class ClientWrapper(ClientMixin):  # type: ignore[misc]
    """authlib's view of a registry row: public client, code+PKCE only."""

    def __init__(self, row: OAuthClient) -> None:
        self._row = row

    @property
    def row(self) -> OAuthClient:
        return self._row

    def get_client_id(self) -> str:
        return self._row.client_id

    def get_default_redirect_uri(self) -> None:
        # never default: redirect_uri is a required, exactly-matched parameter
        return None

    def get_allowed_scope(self, scope: str) -> str:
        # scopes are unused in D08; whatever is asked, nothing is granted
        return ""

    def check_redirect_uri(self, redirect_uri: str) -> bool:
        # EXACT string membership in the seeded registry - no wildcards, no
        # substring or prefix logic, ever (non-negotiable 3)
        return redirect_uri in self._row.redirect_uris

    def check_client_secret(self, client_secret: str) -> bool:
        return False  # public clients hold no secret; PKCE is the proof

    def check_endpoint_auth_method(self, method: str, endpoint: str) -> bool:
        return method == "none"

    def check_response_type(self, response_type: str) -> bool:
        return response_type == "code"

    def check_grant_type(self, grant_type: str) -> bool:
        return grant_type in ("authorization_code", "refresh_token")


class CodeWrapper(AuthorizationCodeMixin):  # type: ignore[misc]
    """authlib's view of an (already atomically consumed) oauth_codes row."""

    def __init__(self, row: OAuthCode) -> None:
        self._row = row

    def get_redirect_uri(self) -> str:
        return self._row.redirect_uri

    def get_scope(self) -> str:
        return self._row.scope

    @property
    def code_challenge(self) -> str:
        return self._row.code_challenge

    @property
    def code_challenge_method(self) -> str:
        return self._row.code_challenge_method


@dataclass
class RequestContext:
    """Rows prefetched by the router; the only state authlib's hooks see."""

    client: ClientWrapper | None = None
    code: OAuthCode | None = None
    subject: TokenSubject | None = None
    # D09: refresh rotation result (refresh grant) or freshly-minted family
    # (code grant). new_refresh_token rides into the token response;
    # issued_family_id lets the router clean up when authlib rejects late.
    rotation: RefreshRotation | None = None
    new_refresh_token: str | None = None
    issued_family_id: uuid.UUID | None = None


class S256CodeChallenge(CodeChallenge):  # type: ignore[misc]
    """PKCE with S256 as the only method, required at BOTH endpoints.

    Upstream CodeChallenge lets an authorize request without any
    code_challenge through and only enforces the verifier at /token; a code
    minted without a challenge would be exchangeable without proof, so the
    authorize side must refuse first (non-negotiable 1).
    """

    SUPPORTED_CODE_CHALLENGE_METHOD = ["S256"]
    DEFAULT_CODE_CHALLENGE_METHOD = "S256"

    def validate_code_challenge(self, grant: Any, redirect_uri: str) -> None:
        payload = grant.request.payload
        if not payload.data.get("code_challenge"):
            raise InvalidRequestError("Missing 'code_challenge'")
        if payload.data.get("code_challenge_method") != "S256":
            raise InvalidRequestError("Only 'S256' code_challenge_method is supported")
        super().validate_code_challenge(grant, redirect_uri)


class AgriAuthorizationCodeGrant(grants.AuthorizationCodeGrant):  # type: ignore[misc]
    TOKEN_ENDPOINT_AUTH_METHODS = ["none"]

    def save_authorization_code(self, code: str, request: OAuth2Request) -> None:
        # /authorize cannot reach this without a session (D09); until then
        # codes are minted only by oauth_service.create_authorization_code
        raise NotImplementedError("D08 issues codes via oauth_service, not /authorize")

    def query_authorization_code(self, code: str, client: ClientWrapper) -> CodeWrapper | None:
        row = self.server.ctx.code
        # reuse, expiry, and client binding were all settled by the atomic
        # consume in the router; this only proves the row is THIS request's
        if row is not None and hash_code(code) == row.code_hash:
            return CodeWrapper(row)
        return None

    def delete_authorization_code(self, authorization_code: CodeWrapper) -> None:
        pass  # consumed atomically before authlib ran; nothing left to do

    def authenticate_user(self, authorization_code: CodeWrapper) -> TokenSubject | None:
        subject: TokenSubject | None = self.server.ctx.subject
        return subject  # None (suspended/missing) -> invalid_grant


class RefreshCredentialWrapper:
    """authlib's view of an already-rotated sessions_refresh lineage. The
    atomic rotation in the router settled reuse/expiry/binding; this only
    confirms the prefetched result belongs to THIS request."""

    def __init__(self, rotation: RefreshRotation) -> None:
        self.rotation = rotation

    def check_client(self, client: ClientWrapper) -> bool:
        # client binding was enforced by the atomic rotation's WHERE clause
        # (token_hash AND client_id); a rotation result only exists for the
        # client the router prefetched, which is the one authlib holds here
        return True

    def get_scope(self) -> str:
        return ""


class AgriRefreshTokenGrant(grants.RefreshTokenGrant):  # type: ignore[misc]
    TOKEN_ENDPOINT_AUTH_METHODS = ["none"]
    INCLUDE_NEW_REFRESH_TOKEN = True

    def authenticate_refresh_token(self, refresh_token: str) -> RefreshCredentialWrapper | None:
        rotation = self.server.ctx.rotation
        if rotation is None:
            return None  # rotation failed in prefetch -> invalid_grant
        return RefreshCredentialWrapper(rotation)

    def authenticate_user(self, credential: RefreshCredentialWrapper) -> TokenSubject | None:
        subject: TokenSubject | None = self.server.ctx.subject
        return subject

    def revoke_old_credential(self, credential: RefreshCredentialWrapper) -> None:
        pass  # rotated atomically in the router before authlib ran


def _generate_access_token(
    grant_type: str,
    client: ClientWrapper,
    user: TokenSubject | None = None,
    scope: str | None = None,
    expires_in: int | None = None,
) -> dict[str, Any]:
    """RS256 access token (D08.D). sub is the internal user UUID - downstream
    services see it, browsers never do (profile responses expose agri_id).
    The refresh_token key is attached by the server's ctx-aware generator
    closure, never here."""
    assert user is not None  # authenticate_user returned it or authlib raised
    key = get_signing_key()
    now = int(time.time())
    claims = {
        "iss": get_settings().oauth_issuer,
        "sub": str(user.user_id),
        "aud": client.get_client_id(),
        "agri_id": user.agri_id,
        "roles": list(user.roles),
        "iat": now,
        "exp": now + ACCESS_TOKEN_TTL_SECONDS,
    }
    if user.name:
        claims["name"] = user.name
    access_token = jwt.encode({"alg": "RS256", "kid": key.kid, "typ": "JWT"}, claims, key)
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": ACCESS_TOKEN_TTL_SECONDS,
    }


class AgriAuthorizationServer(AuthorizationServer):  # type: ignore[misc]
    """One instance per request, holding that request's prefetched context."""

    def __init__(self, ctx: RequestContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.register_grant(AgriAuthorizationCodeGrant, [S256CodeChallenge(required=True)])
        self.register_grant(AgriRefreshTokenGrant)

        def _token_with_refresh(
            grant_type: str,
            client: ClientWrapper,
            user: TokenSubject | None = None,
            scope: str | None = None,
            expires_in: int | None = None,
            include_refresh_token: bool = True,
        ) -> dict[str, Any]:
            token = _generate_access_token(grant_type, client, user, scope, expires_in)
            # D09: the router minted/rotated the opaque refresh credential;
            # this closure is the only place its plaintext joins a response
            if self.ctx.new_refresh_token is not None:
                token["refresh_token"] = self.ctx.new_refresh_token
            return token

        self.register_token_generator("default", _token_with_refresh)

    def query_client(self, client_id: str) -> ClientWrapper | None:
        client = self.ctx.client
        if client is not None and client.get_client_id() == client_id:
            return client
        return None

    def save_token(self, token: dict[str, Any], request: OAuth2Request) -> None:
        pass  # access tokens are stateless JWTs; nothing is persisted in D08

    def send_signal(self, name: str, *args: Any, **kwargs: Any) -> None:
        pass

    def create_oauth2_request(self, request: Any) -> OAuth2Request:
        if not isinstance(request, OAuth2Request):
            raise TypeError("router must pass a prebuilt OAuth2Request")
        return request

    def handle_response(self, status: int, body: Any, headers: Any) -> Response:
        header_map = dict(headers or [])
        if isinstance(body, dict):
            return JSONResponse(body, status_code=status, headers=header_map)
        return Response(content=body or "", status_code=status, headers=header_map)


def build_oauth2_request(
    method: str,
    uri: str,
    params: dict[str, str],
    datalist: dict[str, list[str]],
) -> OAuth2Request:
    """OAuth2Request from already-extracted parameters.

    `params` doubles as the form mapping (the token grant reads code and
    code_verifier through request.form); `datalist` keeps repeated query
    parameters visible so authlib's multiple-parameter check still bites.
    """
    request = OAuth2Request(method, uri)
    payload = BasicOAuth2Payload(params)
    payload._datalist = datalist
    request.payload = payload
    request._body = params
    return request
