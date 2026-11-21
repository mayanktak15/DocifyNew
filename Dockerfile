FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/docify
COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/infra.txt -r requirements/bot.txt
COPY app.py ./
COPY app/ app/
COPY chatbot/ chatbot/
COPY bots/ bots/
COPY data/ data/
COPY tasks/ tasks/
COPY migrations/ migrations/
RUN useradd --create-home --uid 10001 docify && mkdir instance && chown docify:docify instance
USER docify
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:create_app()"]
