FROM python:3.12.10-slim@sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db
ENV PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHONUTF8=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 MPLBACKEND=Agg NPY_DISABLE_CPU_FEATURES=X86_V4
WORKDIR /opt/jpm
COPY requirements-lock.txt ./
RUN python -m pip install --require-hashes --no-deps --no-cache-dir -r requirements-lock.txt && python -m pip check
WORKDIR /app
CMD ["python", "-X", "utf8", "-u", "reproduce_complete.py", "--raw-root", "/raw"]
