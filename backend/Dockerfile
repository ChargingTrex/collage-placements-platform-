FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Requirements first so a code change does not re-run the dependency install.
COPY requirements.txt requirements-nlp.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# The spaCy model is a 40MB download. Build with
#   docker compose build --build-arg INSTALL_NLP=true
# to bake it in; otherwise the engine runs on its TF-IDF fallback.
ARG INSTALL_NLP=false
RUN if [ "$INSTALL_NLP" = "true" ]; then \
        pip install -r requirements-nlp.txt && \
        python -m spacy download en_core_web_md; \
    fi

COPY . .

EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py runserver 0.0.0.0:8000"]
