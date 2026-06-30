from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage
from django.urls import reverse


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


def notify_new_signup(request, user):
    display_name = user.get_full_name() or user.username
    admin_url = request.build_absolute_uri(reverse("admin:auth_user_change", args=[user.pk]))
    body = (
        "A new user signed up for Radiant Ensemble and is awaiting approval.\n\n"
        f"Username: {user.username}\n"
        f"Display name: {display_name}\n"
        f"Admin review link: {admin_url}\n"
    )
    return send_active_user_notification("Radiant Ensemble new user signup", body)


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
