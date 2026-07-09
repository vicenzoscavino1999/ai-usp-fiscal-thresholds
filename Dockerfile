FROM python:3.12.4-slim@sha256:a3e58f9399353be051735f09be0316bfdeab571a5c6a24fd78b92df85bcb2d85

ENV PYTHONHASHSEED=0
ENV OMP_NUM_THREADS=1
ENV MKL_NUM_THREADS=1
ENV OPENBLAS_NUM_THREADS=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends make \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-lock.txt pyproject.toml README.md ./
COPY src/ ./src/

RUN python -m pip install --upgrade pip \
    && pip install --require-hashes -r requirements-lock.txt \
    && pip install --no-deps -e .

COPY . .

CMD ["make", "check-env"]
