import os
from datetime import datetime
from jinja2 import Template

from .logging_setup import setup_logger

logger = setup_logger()

# --------------------------------------------------------------------
# Inline-styled HTML (safe for Gmail/Outlook)
# --------------------------------------------------------------------

EMAIL_TEMPLATE = Template("""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8" />
    <title>Daily Brief</title>
</head>

<body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background: #f5f5f5;">

    <div style="max-width: 760px; margin: auto; padding: 20px;">

        <h1 style="text-align: center; font-size: 24px; margin-bottom: 40px;">
            Daily Brief - {{ date }}
        </h1>

        {% for topic, items in grouped.items() %}
            {% if items %}
                <h2 style="font-size: 20px; margin-top: 40px; margin-bottom: 20px; border-bottom: 2px solid #ddd; padding-bottom: 6px;">
                    {{ topic }}
                </h2>

                {% for it in items %}
                    <div style="
                        background: #ffffff;
                        padding: 16px;
                        margin-bottom: 20px;
                        border: 1px solid #e0e0e0;
                        border-radius: 8px;">


                        <!-- TITLE -->
                        <div style="font-size: 16px; font-weight: bold; margin-bottom: 6px;">
                            <a href="{{ it.url }}" style="color: #1a0dab; text-decoration: none;">
                                {{ it.title }}
                            </a>
                        </div>

                        <!-- SOURCE NAME -->
                        <div style="font-size: 13px; color: #777; margin-bottom: 10px;">
                            {{ it.source }}
                        </div>

                        {% if it.summary_failed %}
                            <!-- FALLBACK CARD WHEN SUMMARIZATION FAILS -->
                            <div style="
                                background: #f3f3f3;
                                padding: 10px 12px;
                                border-left: 4px solid #999;
                                border-radius: 4px;
                                font-size: 14px;
                                color: #444;">
                                This article could not be summarized automatically.
                                The full text may require a browser view or permissions.
                            </div>

                        {% else %}
                            <!-- THREE-SENTENCE SUMMARY -->
                            <div style="font-size: 14px; line-height: 1.45; color: #333;">
                                <p style="margin: 0 0 8px 0;">{{ it.s1 }}</p>
                                {% if it.s2 %}<p style="margin: 0 0 8px 0;">{{ it.s2 }}</p>{% endif %}
                                {% if it.s3 %}<p style="margin: 0;">{{ it.s3 }}</p>{% endif %}
                            </div>
                        {% endif %}

                    </div>
                {% endfor %}
            {% endif %}
        {% endfor %}

    </div>
</body>
</html>
""")


# --------------------------------------------------------------------
# RENDER
# --------------------------------------------------------------------

def render_email(grouped, timezone_label):
    """
    grouped = {
      "World": [
         { "url": ..., "title": ..., "source": ...,
           "s1":..., "s2":..., "s3":..., "summary_failed": bool },
         ...
      ],
      ...
    }
    """

    try:
        now = datetime.now().strftime("%Y-%m-%d")
        html = EMAIL_TEMPLATE.render(
            grouped=grouped,
            date=now,
            tz=timezone_label
        )
        logger.info("HTML email rendered successfully.")
        return html

    except Exception as e:
        logger.error(f"Render error: {e}")
        return "<html><body><p>Render error.</p></body></html>"
