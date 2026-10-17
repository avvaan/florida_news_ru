# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Django 5 + server-rendered templates, plain CSS, no JS framework (requested by the owner in the brief). PostgreSQL in production, SQLite locally. Background work via management commands on a schedule (Render Cron).

## Users

Russian- and Ukrainian-speaking residents of Florida — Miami / Sunny Isles / Aventura, Orlando, Tampa, Jacksonville. Many read English local news poorly. They mostly read on phones, often outdoors in bright light, and want to know quickly: is something threatening me, what changed in the rules, what's happening in my city, what should I do.

The owner/editor spends at most ~10 minutes a day reviewing the «На проверку» queue in Django admin.

## Product Purpose

«Флорида Сегодня»: every 2–3 hours the system collects news from local media and official Florida sources, selects what matters to the audience, writes its own short Russian note (80–150 words) per story with links to the original sources, and publishes to the site and a Telegram channel. Success = readers get safety-critical and life-changing information in Russian within hours, with near-zero manual work.

## Positioning

Not a translation feed: own short retellings in plain Russian with practical "what to do" guidance, always linking the original sources, prioritised by urgency for this audience (hurricanes and evacuations first, then laws, money, city life).

## Constraints

- Never republish full articles or photos from others' articles. Covers are our own Higgsfield illustrations plus licensed Freepik/Magnific stock photos, captioned as illustrative.
- Facts only from sources; sensitive topics (crime, private persons, children, accusations) always go through manual review.
- Nothing is published to the real Telegram channel or a real domain without the owner's explicit confirmation (Telegram is a dry-run until enabled in admin).
- Disclaimer: «Мы пересказываем новости своими словами и всегда даём ссылку на первоисточник; это не юридическая и не финансовая консультация».

## Brand commitments

- Name: «Флорида Сегодня» (confirmed by the owner).
- Visual tone confirmed by the owner: «Флоридский портал» — classic news-portal structure with its own Florida character (gulf/sky colours, storm orange reserved for urgency, one consistent set of rubric illustrations generated in Higgsfield; the owner later asked to add licensed stock photos from Magnific/Freepik to the pools).
