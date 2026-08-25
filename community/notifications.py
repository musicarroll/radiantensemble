import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage, send_mail
from django.urls import reverse


logger = logging.getLogger(__name__)


def active_user_notification_recipients():
    recipients = set()
    users = get_user_model().objects.filter(is_active=True).select_related("member_profile")
    for user in users:
        email = (user.email or "").strip()
        profile = getattr(user, "member_profile", None)
        if not email and profile:
            email = (profile.email or "").strip()
        if email:
            recipients.add(email)
    return sorted(recipients)


def user_notification_email(user):
    email = (user.email or "").strip()
    profile = getattr(user, "member_profile", None)
    if not email and profile:
        email = (profile.email or "").strip()
    return email


def send_active_user_notification(subject, body):
    recipients = active_user_notification_recipients()
    if not recipients:
        return 0
    message = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[settings.SERVER_EMAIL],
        bcc=recipients,
    )
    return message.send(fail_silently=True)


def send_user_notification(recipients, subject, body):
    emails = sorted(
        {
            email
            for user in recipients
            if user.is_active
            for email in [user_notification_email(user)]
            if email
        }
    )
    if not emails:
        return 0
    message = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[settings.SERVER_EMAIL],
        bcc=emails,
    )
    return message.send(fail_silently=True)


def visible_content_notification_recipients(item):
    users = get_user_model().objects.filter(is_active=True).select_related("member_profile")
    return [user for user in users if item.is_visible_to(user)]


def notify_new_signup(request, user):
    display_name = user.get_full_name() or user.username
    admin_url = request.build_absolute_uri(reverse("admin:auth_user_change", args=[user.pk]))
    body = (
        "A new user signed up for Radiant Ensemble and is awaiting approval.\n\n"
        f"Username: {user.username}\n"
        f"Display name: {display_name}\n"
        f"Admin review link: {admin_url}\n"
    )
    try:
        return send_mail(
            subject="Radiant Ensemble new user signup",
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.ADMIN_SIGNUP_NOTIFICATION_EMAIL],
            fail_silently=True,
        )
    except Exception:
        logger.exception("Failed to send new user signup email.")
        return 0


def notify_new_home_post(request, post):
    author = post.owner.get_full_name() or post.owner.username
    home_url = request.build_absolute_uri(reverse("home"))
    title = post.title or "Untitled post"
    excerpt = post.body[:400]
    if len(post.body) > 400:
        excerpt += "..."
    body = (
        "A member posted a new update on the Radiant Ensemble home page.\n\n"
        f"Author: {author}\n"
        f"Title: {title}\n"
        f"Visibility: {post.get_visibility_display()}\n\n"
        f"{excerpt}\n\n"
        f"View the home page: {home_url}\n"
    )
    return send_active_user_notification("Radiant Ensemble new home post", body)


def _artifact_notification_body(request, artifact, action):
    owner = artifact.owner.get_full_name() or artifact.owner.username
    artifacts_url = request.build_absolute_uri(reverse("artifacts"))
    search_url = request.build_absolute_uri(reverse("artifact_search"))
    description = artifact.description[:400]
    if len(artifact.description) > 400:
        description += "..."
    body = (
        f"An artifact was {action} on Radiant Ensemble.\n\n"
        f"Title: {artifact.title}\n"
        f"Owner: {owner}\n"
        f"Type: {artifact.get_artifact_type_display()}\n"
        f"Visibility: {artifact.get_visibility_display()}\n"
    )
    if artifact.original_filename or artifact.file:
        body += f"File: {artifact.original_filename or artifact.file.name}\n"
    if artifact.tags:
        body += f"Tags: {artifact.tags}\n"
    if description:
        body += f"\n{description}\n"
    body += (
        f"\nView artifacts: {artifacts_url}\n"
        f"Search artifacts: {search_url}\n"
    )
    return body


def notify_artifact_uploaded(request, artifact):
    recipients = visible_content_notification_recipients(artifact)
    return send_user_notification(
        recipients,
        "Radiant Ensemble artifact uploaded",
        _artifact_notification_body(request, artifact, "uploaded"),
    )


def notify_artifact_updated(request, artifact):
    recipients = visible_content_notification_recipients(artifact)
    return send_user_notification(
        recipients,
        "Radiant Ensemble artifact updated",
        _artifact_notification_body(request, artifact, "updated"),
    )


def _event_detail_lines(event):
    submitter = event.submitted_by.get_full_name() or event.submitted_by.username
    lines = [
        f"Title: {event.title}",
        f"Submitted by: {submitter}",
        f"Date: {event.event_date}",
        f"Time: {event.event_time.strftime('%H:%M')}",
        f"Visibility: {event.get_visibility_display()}",
        f"Repeat: {event.get_repeat_display()}",
    ]
    if event.location:
        lines.append(f"Location: {event.location}")
    if event.description:
        description = event.description[:400]
        if len(event.description) > 400:
            description += "..."
        lines.extend(["", description])
    return "\n".join(lines)


def _event_links(request, event):
    event_url = request.build_absolute_uri(reverse("event_detail", args=[event.pk]))
    calendar_url = request.build_absolute_uri(
        f"{reverse('calendar')}?year={event.event_date.year}&month={event.event_date.month}"
    )
    return f"View event: {event_url}\nView calendar: {calendar_url}\n"


def notify_event_created(request, event):
    body = (
        "A new event was created on Radiant Ensemble.\n\n"
        f"{_event_detail_lines(event)}\n\n"
        f"{_event_links(request, event)}"
    )
    return send_active_user_notification("Radiant Ensemble event created", body)


def notify_event_updated(request, event):
    body = (
        "An event was updated on Radiant Ensemble.\n\n"
        f"{_event_detail_lines(event)}\n\n"
        f"{_event_links(request, event)}"
    )
    return send_active_user_notification("Radiant Ensemble event updated", body)


def notify_event_deleted(request, event, *, occurrence_date=None):
    calendar_date = occurrence_date or event.event_date
    calendar_url = request.build_absolute_uri(
        f"{reverse('calendar')}?year={calendar_date.year}&month={calendar_date.month}"
    )
    if occurrence_date:
        heading = "An event occurrence was removed from the Radiant Ensemble calendar."
        subject = "Radiant Ensemble event occurrence deleted"
        occurrence_line = f"Removed occurrence: {occurrence_date}\n"
    else:
        heading = "An event was deleted from the Radiant Ensemble calendar."
        subject = "Radiant Ensemble event deleted"
        occurrence_line = ""
    body = (
        f"{heading}\n\n"
        f"{_event_detail_lines(event)}\n"
        f"{occurrence_line}\n"
        f"View calendar: {calendar_url}\n"
    )
    return send_active_user_notification(subject, body)


def notify_direct_message(request, message):
    sender = message.sender.get_full_name() or message.sender.username
    thread_url = request.build_absolute_uri(reverse("thread_page", args=[message.thread_id]))
    excerpt = message.body[:400] if message.body else "Attachment sent."
    if len(message.body) > 400:
        excerpt += "..."
    body = (
        "You received a new direct message on Radiant Ensemble.\n\n"
        f"From: {sender}\n"
        f"Thread: {message.thread.title or 'Direct message'}\n\n"
        f"{excerpt}\n\n"
        f"Open the message thread: {thread_url}\n"
    )
    recipients = message.thread.participants.exclude(pk=message.sender_id)
    return send_user_notification(recipients, "Radiant Ensemble new direct message", body)
