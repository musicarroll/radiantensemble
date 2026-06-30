import json
from calendar import Calendar, month_name
from datetime import date, datetime, time
from urllib import parse, request as urlrequest

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import (
    ArtifactSearchForm,
    BugReportForm,
    ContactForm,
    EventForm,
    FeatureRequestForm,
    MemberProfileForm,
    MemberProfileLinkFormSet,
    PendingUserCreationForm,
)
from .models import (
    Artifact,
    BugReport,
    Event,
    EventCancellation,
    FeatureRequest,
    MemberProfile,
    Message,
    MessageThread,
    Post,
    Visibility,
)
from .utils import calculate_sha256, detect_mime_type, sign_artifact_metadata


def home(request):
    if not request.user.is_authenticated:
        return redirect("about")
    return render(request, "community/home.html")


def about(request):
    return render(request, "community/about.html")


def signup(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = PendingUserCreationForm(request.POST or None)
    turnstile_error = ""
    if request.method == "POST" and form.is_valid():
        remote_ip = _client_ip(request)
        success, turnstile_error = _verify_turnstile(
            request.POST.get("cf-turnstile-response", ""),
            remote_ip,
            "sign up",
        )
        if success:
            user = form.save(commit=False)
            user.is_active = False
            user.save()
            return render(request, "community/signup_pending.html", {"new_user": user})
    return render(
        request,
        "community/signup.html",
        {
            "form": form,
            "turnstile_error": turnstile_error,
            "turnstile_site_key": settings.CF_TURNSTILE_SITE_KEY,
            "turnstile_enabled": settings.CF_TURNSTILE_ENABLED,
        },
    )


def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _verify_turnstile(token, remote_ip=None, form_label="form"):
    if not settings.CF_TURNSTILE_ENABLED:
        return True, ""
    if not settings.CF_TURNSTILE_SECRET_KEY:
        return False, f"{form_label.title()} verification is not configured yet."
    if not token:
        return False, "Please complete the verification challenge."

    payload = {
        "secret": settings.CF_TURNSTILE_SECRET_KEY,
        "response": token,
    }
    if remote_ip:
        payload["remoteip"] = remote_ip
    data = parse.urlencode(payload).encode()
    try:
        req = urlrequest.Request("https://challenges.cloudflare.com/turnstile/v0/siteverify", data=data, method="POST")
        with urlrequest.urlopen(req, timeout=8) as response:
            result = json.loads(response.read().decode())
    except Exception:
        return False, f"Unable to verify the {form_label} challenge. Please try again."
    if result.get("success"):
        return True, ""
    return False, "Verification failed. Please try again."


def contact(request):
    form = ContactForm(request.POST or None)
    turnstile_error = ""
    if request.method == "POST" and form.is_valid():
        remote_ip = _client_ip(request)
        success, turnstile_error = _verify_turnstile(
            request.POST.get("cf-turnstile-response", ""),
            remote_ip,
            "contact form",
        )
        if success:
            message = form.save(commit=False)
            message.remote_addr = remote_ip
            message.user_agent = request.META.get("HTTP_USER_AGENT", "")
            message.turnstile_success = True
            message.save()
            return render(request, "community/contact_success.html", {"message": message})
    return render(
        request,
        "community/contact.html",
        {
            "form": form,
            "turnstile_error": turnstile_error,
            "turnstile_site_key": settings.CF_TURNSTILE_SITE_KEY,
            "turnstile_enabled": settings.CF_TURNSTILE_ENABLED,
        },
    )


def _month_bounds(year, month):
    first_day = date(year, month, 1)
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    return first_day, next_month - timezone.timedelta(days=1)


def _month_nav(year, month):
    previous_month = 12 if month == 1 else month - 1
    previous_year = year - 1 if month == 1 else year
    next_month = 1 if month == 12 else month + 1
    next_year = year + 1 if month == 12 else year
    return previous_year, previous_month, next_year, next_month


def _event_occurrences_for_range(events, start_date, end_date):
    occurrences = []
    current = start_date
    while current <= end_date:
        for event in events:
            if event.occurs_on(current):
                occurrences.append({"event": event, "date": current})
        current += timezone.timedelta(days=1)
    return sorted(occurrences, key=lambda item: (item["date"], item["event"].event_time, item["event"].title))


@login_required
def calendar_page(request):
    today = timezone.localdate()
    try:
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))
        first_day, last_day = _month_bounds(year, month)
    except ValueError:
        year = today.year
        month = today.month
        first_day, last_day = _month_bounds(year, month)

    events = [event for event in Event.objects.select_related("submitted_by") if event.is_visible_to(request.user)]
    occurrences = _event_occurrences_for_range(events, first_day, last_day)
    occurrences_by_date = {}
    for occurrence in occurrences:
        occurrences_by_date.setdefault(occurrence["date"], []).append(occurrence)

    calendar_weeks = []
    for week in Calendar(firstweekday=6).monthdatescalendar(year, month):
        calendar_weeks.append([
            {
                "date": day,
                "in_month": day.month == month,
                "occurrences": occurrences_by_date.get(day, []),
            }
            for day in week
        ])

    previous_year, previous_month, next_year, next_month = _month_nav(year, month)
    return render(
        request,
        "community/calendar.html",
        {
            "calendar_weeks": calendar_weeks,
            "month_name": month_name[month],
            "year": year,
            "previous_year": previous_year,
            "previous_month": previous_month,
            "next_year": next_year,
            "next_month": next_month,
        },
    )


@login_required
def add_event(request):
    form = EventForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        event = form.save(commit=False)
        event.submitted_by = request.user
        event.save()
        return redirect("event_detail", event_id=event.pk)
    return render(request, "community/event_form.html", {"form": form, "page_title": "Add Event"})


def _can_manage_event(user, event):
    return user.is_authenticated and (user.is_staff or event.submitted_by == user)


@login_required
def edit_event(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if not _can_manage_event(request.user, event):
        raise Http404("Event not found")
    form = EventForm(request.POST or None, instance=event)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("event_detail", event_id=event.pk)
    return render(request, "community/event_form.html", {"form": form, "event": event, "page_title": "Edit Event"})


@login_required
@require_http_methods(["POST"])
def delete_event(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if not _can_manage_event(request.user, event):
        raise Http404("Event not found")
    event.delete()
    return redirect("calendar")


@login_required
@require_http_methods(["POST"])
def delete_event_occurrence(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if not _can_manage_event(request.user, event):
        raise Http404("Event not found")
    try:
        occurrence_date = date.fromisoformat(request.POST.get("occurrence_date", ""))
    except ValueError:
        raise Http404("Event occurrence not found")
    if not event.occurs_on(occurrence_date):
        raise Http404("Event occurrence not found")
    if event.repeat == Event.RepeatRule.NONE:
        event.delete()
    else:
        EventCancellation.objects.get_or_create(
            event=event,
            occurrence_date=occurrence_date,
            defaults={"cancelled_by": request.user},
        )
    return redirect(f"{reverse('calendar')}?year={occurrence_date.year}&month={occurrence_date.month}")


def upcoming_events(request):
    today = timezone.localdate()
    occurrences = []
    for event in Event.objects.filter(visibility=Event.EventVisibility.PUBLIC).select_related("submitted_by"):
        occurrence_date = event.next_occurrence_on_or_after(today)
        if occurrence_date:
            occurrences.append({"event": event, "date": occurrence_date})
    occurrences.sort(key=lambda item: (item["date"], item["event"].event_time, item["event"].title))
    return render(request, "community/upcoming_events.html", {"occurrences": occurrences})


def event_detail(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if not event.is_visible_to(request.user):
        raise Http404("Event not found")
    occurrence_date = event.event_date
    requested_date = request.GET.get("date")
    if requested_date:
        try:
            parsed_date = date.fromisoformat(requested_date)
            if not event.occurs_on(parsed_date):
                raise Http404("Event occurrence not found")
            occurrence_date = parsed_date
        except ValueError:
            pass
    return render(
        request,
        "community/event_detail.html",
        {
            "event": event,
            "occurrence_date": occurrence_date,
            "can_manage_event": _can_manage_event(request.user, event),
        },
    )


@login_required
def bug_report_list(request):
    reports = BugReport.objects.select_related("submitted_by").all()
    return render(request, "community/bug_report_list.html", {"reports": reports})


@login_required
def bug_report_create(request):
    form = BugReportForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        report = form.save(commit=False)
        report.submitted_by = request.user
        report.save()
        return redirect("bug_report_detail", report_id=report.pk)
    return render(request, "community/work_item_form.html", {"form": form, "page_title": "Report a Bug"})


@login_required
def bug_report_detail(request, report_id):
    report = get_object_or_404(BugReport.objects.select_related("submitted_by"), pk=report_id)
    return render(request, "community/bug_report_detail.html", {"report": report})


@login_required
def feature_request_list(request):
    requests = FeatureRequest.objects.select_related("submitted_by").all()
    return render(request, "community/feature_request_list.html", {"requests": requests})


@login_required
def feature_request_create(request):
    form = FeatureRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        feature = form.save(commit=False)
        feature.submitted_by = request.user
        feature.save()
        return redirect("feature_request_detail", request_id=feature.pk)
    return render(request, "community/work_item_form.html", {"form": form, "page_title": "Request a Feature"})


@login_required
def feature_request_detail(request, request_id):
    feature = get_object_or_404(FeatureRequest.objects.select_related("submitted_by"), pk=request_id)
    return render(request, "community/feature_request_detail.html", {"feature": feature})


@login_required
def member_list(request):
    profiles = MemberProfile.objects.select_related("user").prefetch_related("links").all()
    return render(request, "community/member_list.html", {"profiles": profiles})


@login_required
def member_page(request, slug):
    profile = get_object_or_404(MemberProfile, slug=slug)
    posts = [post for post in Post.objects.filter(owner=profile.user) if post.is_visible_to(request.user)]
    artifacts = [artifact for artifact in Artifact.objects.filter(owner=profile.user) if artifact.is_visible_to(request.user)]
    return render(
        request,
        "community/member_page.html",
        {"profile": profile, "posts": posts, "artifacts": artifacts},
    )


@login_required
def edit_profile(request):
    profile, _created = MemberProfile.objects.get_or_create(
        user=request.user,
        defaults={"display_name": request.user.get_full_name() or request.user.username},
    )
    form = MemberProfileForm(request.POST or None, request.FILES or None, instance=profile)
    formset = MemberProfileLinkFormSet(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        form.save()
        formset.save()
        return redirect("member_page", slug=profile.slug)
    return render(request, "community/profile_form.html", {"form": form, "formset": formset, "profile": profile})


@login_required
def thread_page(request, thread_id):
    get_object_or_404(MessageThread, pk=thread_id, participants=request.user)
    return render(request, "community/thread_page.html", {"thread_id": thread_id})


def _user_payload(user):
    profile = getattr(user, "member_profile", None)
    return {
        "id": user.pk,
        "username": user.username,
        "displayName": profile.display_name if profile else (user.get_full_name() or user.username),
        "profileUrl": profile.get_absolute_url() if profile else "",
        "accentColor": profile.accent_color if profile else "#7c3aed",
        "isStaff": user.is_staff,
    }


def _post_payload(post):
    return {
        "id": post.pk,
        "title": post.title,
        "body": post.body,
        "owner": _user_payload(post.owner),
        "visibility": post.visibility,
        "pinned": post.pinned,
        "createdAt": post.created_at.isoformat(),
    }


def _artifact_payload(artifact):
    return {
        "id": artifact.pk,
        "title": artifact.title,
        "description": artifact.description,
        "artifactType": artifact.artifact_type,
        "tags": [tag.strip() for tag in artifact.tags.split(",") if tag.strip()],
        "url": artifact.file.url if artifact.file else "",
        "originalFilename": artifact.original_filename,
        "storedFilename": artifact.stored_filename,
        "mimeType": artifact.mime_type,
        "fileSize": artifact.file_size,
        "sha256Checksum": artifact.sha256_checksum,
        "owner": _user_payload(artifact.owner),
        "visibility": artifact.visibility,
        "createdAt": artifact.created_at.isoformat(),
    }


def _message_payload(message):
    return {
        "id": message.pk,
        "sender": _user_payload(message.sender),
        "body": message.body,
        "attachmentUrl": message.attachment.url if message.attachment else "",
        "createdAt": message.created_at.isoformat(),
    }


def _thread_payload(thread):
    participants = list(thread.participants.all())
    last_message = thread.messages.order_by("-created_at").first()
    return {
        "id": thread.pk,
        "title": thread.title or ", ".join(user.username for user in participants),
        "isGroupThread": thread.is_group_thread,
        "participants": [_user_payload(user) for user in participants],
        "lastMessage": last_message.body if last_message else "",
        "updatedAt": thread.updated_at.isoformat(),
    }


def api_me(request):
    return JsonResponse({
        "authenticated": request.user.is_authenticated,
        "user": _user_payload(request.user) if request.user.is_authenticated else None,
        "defaultVisibility": Visibility.MEMBERS,
    })


def api_home_feed(request):
    posts = [_post_payload(post) for post in Post.objects.select_related("owner").all() if post.is_visible_to(request.user)]
    members = [
        _user_payload(profile.user)
        for profile in MemberProfile.objects.select_related("user").filter(user__is_active=True)
        if profile.page_is_public or request.user.is_authenticated
    ]
    return JsonResponse({"posts": posts[:25], "members": members})


def api_artifacts(request):
    artifacts = [
        _artifact_payload(artifact)
        for artifact in Artifact.objects.select_related("owner").all()
        if artifact.is_visible_to(request.user)
    ]
    return JsonResponse({"artifacts": artifacts[:50]})


def _date_bound(value, end_of_day=False):
    if not value:
        return None
    return timezone.make_aware(datetime.combine(value, time.max if end_of_day else time.min))


def artifact_search(request):
    form = ArtifactSearchForm(request.GET or None)
    artifacts = Artifact.objects.select_related("owner").all()
    searched = bool(request.GET)

    if form.is_valid():
        data = form.cleaned_data
        if data["owner"]:
            owner = data["owner"].strip()
            owner_filter = {"owner__username__icontains": owner}
            if owner.isdigit():
                owner_filter = {"owner_id": int(owner)}
            artifacts = artifacts.filter(**owner_filter)
        for field in ("title", "description", "tags"):
            if data[field]:
                artifacts = artifacts.filter(**{f"{field}__icontains": data[field]})
        if data["artifact_type"]:
            artifacts = artifacts.filter(artifact_type=data["artifact_type"])
        if data["visibility"]:
            artifacts = artifacts.filter(visibility=data["visibility"])

        created_after = _date_bound(data["created_after"])
        created_before = _date_bound(data["created_before"], end_of_day=True)
        updated_after = _date_bound(data["updated_after"])
        updated_before = _date_bound(data["updated_before"], end_of_day=True)
        if created_after:
            artifacts = artifacts.filter(created_at__gte=created_after)
        if created_before:
            artifacts = artifacts.filter(created_at__lte=created_before)
        if updated_after:
            artifacts = artifacts.filter(updated_at__gte=updated_after)
        if updated_before:
            artifacts = artifacts.filter(updated_at__lte=updated_before)

    visible_artifacts = [artifact for artifact in artifacts if artifact.is_visible_to(request.user)]
    paginator = Paginator(visible_artifacts, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)

    return render(
        request,
        "community/artifact_search.html",
        {
            "form": form,
            "page_obj": page_obj,
            "searched": searched,
            "query_string": query_params.urlencode(),
        },
    )


@login_required
def api_threads(request):
    threads = [
        _thread_payload(thread)
        for thread in MessageThread.objects.filter(participants=request.user).prefetch_related("participants", "messages")
    ]
    return JsonResponse({"threads": threads})


@login_required
def api_thread_detail(request, thread_id):
    thread = get_object_or_404(
        MessageThread.objects.prefetch_related("participants", "messages__sender"),
        pk=thread_id,
        participants=request.user,
    )
    return JsonResponse({
        "thread": _thread_payload(thread),
        "messages": [_message_payload(message) for message in thread.messages.all()],
    })


@login_required
@require_http_methods(["POST"])
def create_direct_thread(request):
    recipient_id = request.POST.get("recipient_id")
    if not recipient_id:
        return JsonResponse({"error": "Choose a member to message."}, status=400)
    recipient = get_object_or_404(User, pk=recipient_id, is_active=True)
    if recipient == request.user:
        return JsonResponse({"error": "Choose another member to message."}, status=400)
    thread = MessageThread.objects.create(title=request.POST.get("title", ""), is_group_thread=False)
    thread.participants.add(request.user, recipient)
    body = request.POST.get("body", "").strip()
    if body:
        Message.objects.create(thread=thread, sender=request.user, body=body)
    return JsonResponse({"thread": _thread_payload(thread)}, status=201)


@login_required
@require_http_methods(["POST"])
def send_message(request, thread_id):
    thread = get_object_or_404(MessageThread, pk=thread_id, participants=request.user)
    body = request.POST.get("body", "").strip()
    attachment = request.FILES.get("attachment")
    if not body and not attachment:
        return JsonResponse({"error": "Message text or an attachment is required."}, status=400)
    message = Message.objects.create(thread=thread, sender=request.user, body=body, attachment=attachment)
    thread.save(update_fields=["updated_at"])
    return JsonResponse({"message": _message_payload(message), "thread": _thread_payload(thread)}, status=201)


@login_required
@require_http_methods(["POST"])
def create_post(request):
    body = request.POST.get("body", "").strip()
    visibility = request.POST.get("visibility", Visibility.MEMBERS)
    if not body:
        return JsonResponse({"error": "Post body is required."}, status=400)
    if visibility not in Visibility.values:
        return JsonResponse({"error": "Invalid visibility value."}, status=400)

    post = Post.objects.create(
        owner=request.user,
        title=request.POST.get("title", "").strip(),
        body=body,
        visibility=visibility,
        pinned=request.user.is_staff and request.POST.get("pinned") == "true",
    )
    return JsonResponse({"post": _post_payload(post)}, status=201)


@login_required
@require_http_methods(["POST"])
def update_post(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    if post.owner != request.user:
        return JsonResponse({"error": "You can only edit your own posts."}, status=403)

    body = request.POST.get("body", "").strip()
    visibility = request.POST.get("visibility", post.visibility)
    if not body:
        return JsonResponse({"error": "Post body is required."}, status=400)
    if visibility not in Visibility.values:
        return JsonResponse({"error": "Invalid visibility value."}, status=400)

    post.title = request.POST.get("title", "").strip()
    post.body = body
    post.visibility = visibility
    if request.user.is_staff:
        post.pinned = request.POST.get("pinned") == "true"
    post.save(update_fields=["title", "body", "visibility", "pinned", "updated_at"])
    return JsonResponse({"post": _post_payload(post)})


@login_required
@require_http_methods(["POST"])
def delete_post(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    if post.owner != request.user:
        return JsonResponse({"error": "You can only delete your own posts."}, status=403)
    post.delete()
    return JsonResponse({"deleted": True})


@login_required
@require_http_methods(["POST"])
def pin_post(request, post_id):
    if not request.user.is_staff:
        return JsonResponse({"error": "Only staff users can pin posts."}, status=403)
    post = get_object_or_404(Post, pk=post_id)
    post.pinned = request.POST.get("pinned") == "true"
    post.save(update_fields=["pinned", "updated_at"])
    return JsonResponse({"post": _post_payload(post)})


@login_required
@require_http_methods(["POST"])
def upload_artifact(request):
    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        return JsonResponse({"error": "A file upload is required."}, status=400)

    # FileField metadata harvesting order:
    # 1. capture original uploaded name
    # 2. compute checksum
    # 3. detect MIME type
    # 4. record file size
    # 5. save file through Django storage
    # 6. capture final stored name
    # 7. sign harvested metadata
    # 8. save metadata on the model
    original_filename = uploaded_file.name
    sha256_checksum = calculate_sha256(uploaded_file)
    mime_type = detect_mime_type(uploaded_file, original_filename)
    file_size = uploaded_file.size or 0
    try:
        uploaded_file.seek(0)
    except (AttributeError, OSError):
        pass

    artifact = Artifact(
        owner=request.user,
        title=request.POST.get("title") or uploaded_file.name,
        description=request.POST.get("description", ""),
        artifact_type=request.POST.get("artifact_type", Artifact.ArtifactType.OTHER),
        visibility=request.POST.get("visibility", Visibility.MEMBERS),
        tags=request.POST.get("tags", ""),
        original_filename=original_filename,
        mime_type=mime_type,
        file_size=file_size,
        sha256_checksum=sha256_checksum,
    )
    artifact.file.save(uploaded_file.name, uploaded_file, save=False)
    artifact.stored_filename = artifact.file.name
    artifact.metadata_signature = sign_artifact_metadata(
        original_filename=artifact.original_filename,
        stored_filename=artifact.stored_filename,
        mime_type=artifact.mime_type,
        file_size=artifact.file_size,
        sha256_checksum=artifact.sha256_checksum,
    )
    artifact.save()
    return JsonResponse({"artifact": _artifact_payload(artifact)}, status=201)

# Create your views here.
