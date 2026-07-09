FROM python:3.12.4-slim

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
