# Backend truth lives here: Python 3.13. Host Python is tooling only.
FROM python:3.13-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
RUN python -m venv /venv
WORKDIR /src
COPY . .
RUN /venv/bin/pip install .

FROM python:3.13-slim

RUN useradd --create-home --uid 1000 appuser
COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH"
# release tag for sentry/observability; set by CI (deploy-staging.yml)
ARG GIT_SHA=""
ENV RELEASE=$GIT_SHA
USER appuser
WORKDIR /home/appuser
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
