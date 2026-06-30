import hashlib
import shutil
import tempfile
from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from django.urls import reverse
from datetime import date, time

from .models import (
    Artifact,
    BugReport,
    ContactMessage,
    Event,
    EventCancellation,
    FeatureRequest,
    MemberProfileLink,
    MessageThread,
    Post,
    Visibility,
)
from .utils import (
    calculate_sha256,
    detect_mime_type,
    sign_artifact_metadata,
    verify_artifact_metadata_signature,
)


class VisibilityTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="testpass")
        self.member = User.objects.create_user(username="member", password="testpass")
        self.group = Group.objects.create(name="Sopranos")

    def test_public_post_visible_to_anonymous_user(self):
        post = Post.objects.create(owner=self.owner, body="Public note", visibility=Visibility.PUBLIC)
        self.assertTrue(post.is_visible_to(self.client.request().wsgi_request.user))

    def test_members_only_post_hidden_from_anonymous_user(self):
        post = Post.objects.create(owner=self.owner, body="Members note", visibility=Visibility.MEMBERS)
        self.assertFalse(post.is_visible_to(self.client.request().wsgi_request.user))

    def test_group_post_visible_to_group_member(self):
        self.member.groups.add(self.group)
        post = Post.objects.create(owner=self.owner, body="Section note", visibility=Visibility.GROUPS)
        post.visible_to_groups.add(self.group)
        self.assertTrue(post.is_visible_to(self.member))


class PublicPageTests(TestCase):
    def test_anonymous_home_redirects_to_about(self):
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, reverse("about"))

    def test_authenticated_home_loads_member_dashboard(self):
        User.objects.create_user(username="member", password="testpass")
        self.client.login(username="member", password="testpass")
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "radiant-home")

    def test_about_page_loads(self):
        response = self.client.get(reverse("about"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Radiant Ensemble")

    def test_signup_link_shows_for_anonymous_visitors(self):
        response = self.client.get(reverse("about"))
        self.assertContains(response, reverse("signup"))
        self.assertContains(response, "Sign Up")

    @override_settings(CF_TURNSTILE_ENABLED=False)
    def test_signup_creates_inactive_user_when_turnstile_disabled(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "prospective",
                "password1": "safe-test-pass-123",
                "password2": "safe-test-pass-123",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Account Awaiting Approval")
        user = User.objects.get(username="prospective")
        self.assertFalse(user.is_active)
        self.assertFalse(self.client.login(username="prospective", password="safe-test-pass-123"))

    @override_settings(CF_TURNSTILE_ENABLED=True, CF_TURNSTILE_SECRET_KEY="")
    def test_signup_requires_turnstile_configuration_when_enabled(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "prospective",
                "password1": "safe-test-pass-123",
                "password2": "safe-test-pass-123",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign Up verification is not configured yet.")
        self.assertFalse(User.objects.filter(username="prospective").exists())

    def test_signup_redirects_authenticated_users_home(self):
        User.objects.create_user(username="member", password="testpass")
        self.client.login(username="member", password="testpass")
        response = self.client.get(reverse("signup"))
        self.assertRedirects(response, reverse("home"))

    @override_settings(CF_TURNSTILE_ENABLED=False)
    def test_contact_form_saves_when_turnstile_disabled(self):
        response = self.client.post(
            reverse("contact"),
            {
                "name": "Visitor",
                "email": "visitor@example.com",
                "subject": "Booking question",
                "message": "Hello from the public site.",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Message Sent")
        self.assertEqual(ContactMessage.objects.count(), 1)

    @override_settings(CF_TURNSTILE_ENABLED=True, CF_TURNSTILE_SECRET_KEY="")
    def test_contact_form_requires_turnstile_configuration_when_enabled(self):
        response = self.client.post(
            reverse("contact"),
            {
                "name": "Visitor",
                "email": "visitor@example.com",
                "subject": "Booking question",
                "message": "Hello from the public site.",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Contact verification is not configured yet.")
        self.assertEqual(ContactMessage.objects.count(), 0)


class MemberProfileTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(username="profile-member", password="testpass")

    def test_member_list_requires_login(self):
        response = self.client.get(reverse("member_list"))
        self.assertEqual(response.status_code, 302)

    def test_member_detail_requires_login(self):
        response = self.client.get(reverse("member_page", kwargs={"slug": self.member.member_profile.slug}))
        self.assertEqual(response.status_code, 302)

    def test_member_can_view_member_list(self):
        self.client.login(username="profile-member", password="testpass")
        response = self.client.get(reverse("member_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "profile-member")

    def test_member_can_update_own_profile_and_links(self):
        self.client.login(username="profile-member", password="testpass")
        response = self.client.post(
            reverse("edit_profile"),
            {
                "display_name": "Profile Member",
                "bio": "I play guitar.",
                "phone": "555-0100",
                "email": "profile@example.com",
                "accent_color": "#123456",
                "links-TOTAL_FORMS": "3",
                "links-INITIAL_FORMS": "0",
                "links-MIN_NUM_FORMS": "0",
                "links-MAX_NUM_FORMS": "1000",
                "links-0-title": "Interesting Site",
                "links-0-url": "https://example.com",
                "links-0-description": "Worth reading.",
                "links-0-sort_order": "1",
                "links-1-title": "",
                "links-1-url": "",
                "links-1-description": "",
                "links-1-sort_order": "0",
                "links-2-title": "",
                "links-2-url": "",
                "links-2-description": "",
                "links-2-sort_order": "0",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.member.member_profile.refresh_from_db()
        self.assertEqual(self.member.member_profile.display_name, "Profile Member")
        self.assertEqual(self.member.member_profile.phone, "555-0100")
        self.assertEqual(self.member.member_profile.email, "profile@example.com")
        self.assertTrue(MemberProfileLink.objects.filter(profile=self.member.member_profile, title="Interesting Site").exists())


class EventTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(username="member", password="testpass")

    def test_calendar_requires_login(self):
        response = self.client.get(reverse("calendar"))
        self.assertEqual(response.status_code, 302)

    def test_member_can_add_event(self):
        self.client.login(username="member", password="testpass")
        response = self.client.post(
            reverse("add_event"),
            {
                "title": "Rehearsal",
                "description": "Full ensemble",
                "location": "Studio A",
                "event_date": "2026-07-10",
                "event_time": "19:30",
                "visibility": Event.EventVisibility.MEMBERS,
                "repeat": Event.RepeatRule.NONE,
            },
        )
        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(title="Rehearsal")
        self.assertEqual(event.submitted_by, self.member)

    def test_upcoming_events_lists_public_future_events(self):
        Event.objects.create(
            submitted_by=self.member,
            title="Concert",
            description="Public concert",
            location="Main Hall",
            event_date=timezone.localdate() + timezone.timedelta(days=3),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.PUBLIC,
        )
        response = self.client.get(reverse("upcoming_events"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Concert")

    def test_upcoming_events_hides_member_only_events(self):
        Event.objects.create(
            submitted_by=self.member,
            title="Private Rehearsal",
            event_date=timezone.localdate() + timezone.timedelta(days=3),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
        )
        response = self.client.get(reverse("upcoming_events"))
        self.assertNotContains(response, "Private Rehearsal")

    def test_event_detail_hides_member_only_event_from_anonymous_user(self):
        event = Event.objects.create(
            submitted_by=self.member,
            title="Members Only",
            event_date=timezone.localdate(),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
        )
        response = self.client.get(reverse("event_detail", kwargs={"event_id": event.pk}))
        self.assertEqual(response.status_code, 404)

    def test_calendar_shows_weekly_recurring_event_in_month(self):
        Event.objects.create(
            submitted_by=self.member,
            title="Weekly Sectional",
            event_date=date(2026, 7, 1),
            event_time=time(18, 0),
            visibility=Event.EventVisibility.MEMBERS,
            repeat=Event.RepeatRule.WEEKLY,
        )
        self.client.login(username="member", password="testpass")
        response = self.client.get(reverse("calendar"), {"year": 2026, "month": 7})
        self.assertContains(response, "Weekly Sectional", count=5)

    def test_public_recurring_event_appears_on_upcoming_page(self):
        Event.objects.create(
            submitted_by=self.member,
            title="Daily Warmup",
            event_date=timezone.localdate() - timezone.timedelta(days=1),
            event_time=time(9, 0),
            visibility=Event.EventVisibility.PUBLIC,
            repeat=Event.RepeatRule.DAILY,
        )
        response = self.client.get(reverse("upcoming_events"))
        self.assertContains(response, "Daily Warmup")

    def test_monthly_ordinal_event_matches_same_ordinal_weekday(self):
        event = Event.objects.create(
            submitted_by=self.member,
            title="Second Tuesday Planning",
            event_date=date(2026, 7, 14),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
            repeat=Event.RepeatRule.MONTHLY_ORDINAL,
        )
        self.assertTrue(event.occurs_on(date(2026, 8, 11)))
        self.assertFalse(event.occurs_on(date(2026, 8, 14)))

    def test_calendar_shows_monthly_ordinal_event_in_later_month(self):
        Event.objects.create(
            submitted_by=self.member,
            title="Second Tuesday Planning",
            event_date=date(2026, 7, 14),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
            repeat=Event.RepeatRule.MONTHLY_ORDINAL,
        )
        self.client.login(username="member", password="testpass")
        response = self.client.get(reverse("calendar"), {"year": 2026, "month": 8})
        self.assertContains(response, "Second Tuesday Planning", count=1)
        self.assertContains(response, "date=2026-08-11")

    def test_public_monthly_ordinal_event_appears_on_upcoming_page(self):
        Event.objects.create(
            submitted_by=self.member,
            title="Monthly Public Jam",
            event_date=timezone.localdate() - timezone.timedelta(days=35),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.PUBLIC,
            repeat=Event.RepeatRule.MONTHLY_ORDINAL,
        )
        response = self.client.get(reverse("upcoming_events"))
        self.assertContains(response, "Monthly Public Jam")

    def test_event_creator_can_edit_event(self):
        event = Event.objects.create(
            submitted_by=self.member,
            title="Original Event",
            event_date=date(2026, 7, 10),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
        )
        self.client.login(username="member", password="testpass")
        response = self.client.post(
            reverse("edit_event", kwargs={"event_id": event.pk}),
            {
                "title": "Updated Event",
                "description": "Updated",
                "location": "New Room",
                "event_date": "2026-07-11",
                "event_time": "20:00",
                "visibility": Event.EventVisibility.PUBLIC,
                "repeat": Event.RepeatRule.WEEKLY,
            },
        )
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.title, "Updated Event")
        self.assertEqual(event.submitted_by, self.member)

    def test_staff_can_edit_someone_elses_event(self):
        staff = User.objects.create_user(username="staff-event", password="testpass", is_staff=True)
        event = Event.objects.create(
            submitted_by=self.member,
            title="Member Event",
            event_date=date(2026, 7, 10),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
        )
        self.client.login(username="staff-event", password="testpass")
        response = self.client.post(
            reverse("edit_event", kwargs={"event_id": event.pk}),
            {
                "title": "Staff Updated Event",
                "description": "",
                "location": "",
                "event_date": "2026-07-10",
                "event_time": "19:00",
                "visibility": Event.EventVisibility.PUBLIC,
                "repeat": Event.RepeatRule.NONE,
            },
        )
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.title, "Staff Updated Event")
        self.assertEqual(event.submitted_by, self.member)

    def test_non_creator_cannot_edit_event(self):
        other = User.objects.create_user(username="other-event", password="testpass")
        event = Event.objects.create(
            submitted_by=self.member,
            title="Member Event",
            event_date=date(2026, 7, 10),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
        )
        self.client.login(username="other-event", password="testpass")
        response = self.client.get(reverse("edit_event", kwargs={"event_id": event.pk}))
        self.assertEqual(response.status_code, 404)

    def test_event_creator_can_delete_event(self):
        event = Event.objects.create(
            submitted_by=self.member,
            title="Delete Me",
            event_date=date(2026, 7, 10),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
        )
        self.client.login(username="member", password="testpass")
        response = self.client.post(reverse("delete_event", kwargs={"event_id": event.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Event.objects.filter(pk=event.pk).exists())


class WorkItemTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(username="member", password="testpass")

    def test_bug_report_list_requires_login(self):
        response = self.client.get(reverse("bug_report_list"))
        self.assertEqual(response.status_code, 302)

    def test_feature_request_list_requires_login(self):
        response = self.client.get(reverse("feature_request_list"))
        self.assertEqual(response.status_code, 302)

    def test_member_can_create_bug_report(self):
        self.client.login(username="member", password="testpass")
        response = self.client.post(
            reverse("bug_report_create"),
            {
                "title": "Calendar display problem",
                "description": "The calendar layout is unclear.",
                "steps_to_reproduce": "Open the calendar.",
                "expected_behavior": "Readable calendar.",
                "actual_behavior": "Crowded calendar.",
                "page_url": "https://radiantensemble.com/calendar/",
                "severity": "medium",
            },
        )
        self.assertEqual(response.status_code, 302)
        report = BugReport.objects.get(title="Calendar display problem")
        self.assertEqual(report.submitted_by, self.member)

    def test_member_can_view_bug_report_detail(self):
        report = BugReport.objects.create(
            submitted_by=self.member,
            title="Broken link",
            description="A link does not work.",
        )
        self.client.login(username="member", password="testpass")
        response = self.client.get(reverse("bug_report_detail", kwargs={"report_id": report.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Broken link")

    def test_anonymous_cannot_view_bug_report_detail(self):
        report = BugReport.objects.create(
            submitted_by=self.member,
            title="Hidden bug",
            description="Members only.",
        )
        response = self.client.get(reverse("bug_report_detail", kwargs={"report_id": report.pk}))
        self.assertEqual(response.status_code, 302)

    def test_member_can_create_feature_request(self):
        self.client.login(username="member", password="testpass")
        response = self.client.post(
            reverse("feature_request_create"),
            {
                "title": "Add rehearsal reminders",
                "description": "Members should receive reminders.",
                "use_case": "Before a rehearsal.",
                "benefit": "Better attendance.",
                "impact": "important",
            },
        )
        self.assertEqual(response.status_code, 302)
        feature = FeatureRequest.objects.get(title="Add rehearsal reminders")
        self.assertEqual(feature.submitted_by, self.member)

    def test_member_can_view_feature_request_detail(self):
        feature = FeatureRequest.objects.create(
            submitted_by=self.member,
            title="Better artifact search",
            description="Search tags and titles.",
        )
        self.client.login(username="member", password="testpass")
        response = self.client.get(reverse("feature_request_detail", kwargs={"request_id": feature.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Better artifact search")

    def test_anonymous_cannot_view_feature_request_detail(self):
        feature = FeatureRequest.objects.create(
            submitted_by=self.member,
            title="Hidden feature",
            description="Members only.",
        )
        response = self.client.get(reverse("feature_request_detail", kwargs={"request_id": feature.pk}))
        self.assertEqual(response.status_code, 302)

    def test_staff_can_delete_someone_elses_event(self):
        staff = User.objects.create_user(username="staff-delete-event", password="testpass", is_staff=True)
        event = Event.objects.create(
            submitted_by=self.member,
            title="Delete By Staff",
            event_date=date(2026, 7, 10),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
        )
        self.client.login(username="staff-delete-event", password="testpass")
        response = self.client.post(reverse("delete_event", kwargs={"event_id": event.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Event.objects.filter(pk=event.pk).exists())

    def test_non_creator_cannot_delete_event(self):
        other = User.objects.create_user(username="other-delete-event", password="testpass")
        event = Event.objects.create(
            submitted_by=self.member,
            title="Keep Me",
            event_date=date(2026, 7, 10),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
        )
        self.client.login(username="other-delete-event", password="testpass")
        response = self.client.post(reverse("delete_event", kwargs={"event_id": event.pk}))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Event.objects.filter(pk=event.pk).exists())

    def test_creator_can_delete_single_repeated_occurrence(self):
        event = Event.objects.create(
            submitted_by=self.member,
            title="Weekly Rehearsal",
            event_date=date(2026, 7, 1),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
            repeat=Event.RepeatRule.WEEKLY,
        )
        self.client.login(username="member", password="testpass")
        response = self.client.post(
            reverse("delete_event_occurrence", kwargs={"event_id": event.pk}),
            {"occurrence_date": "2026-07-08"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Event.objects.filter(pk=event.pk).exists())
        self.assertTrue(EventCancellation.objects.filter(event=event, occurrence_date=date(2026, 7, 8)).exists())
        self.assertFalse(event.occurs_on(date(2026, 7, 8)))
        self.assertTrue(event.occurs_on(date(2026, 7, 15)))

    def test_cancelled_occurrence_hidden_from_calendar(self):
        event = Event.objects.create(
            submitted_by=self.member,
            title="Weekly Rehearsal",
            event_date=date(2026, 7, 1),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
            repeat=Event.RepeatRule.WEEKLY,
        )
        EventCancellation.objects.create(event=event, occurrence_date=date(2026, 7, 8), cancelled_by=self.member)
        self.client.login(username="member", password="testpass")
        response = self.client.get(reverse("calendar"), {"year": 2026, "month": 7})
        self.assertContains(response, "Weekly Rehearsal", count=4)
        self.assertNotContains(response, "date=2026-07-08")

    def test_staff_can_delete_someone_elses_single_occurrence(self):
        staff = User.objects.create_user(username="staff-cancel-event", password="testpass", is_staff=True)
        event = Event.objects.create(
            submitted_by=self.member,
            title="Weekly Rehearsal",
            event_date=date(2026, 7, 1),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
            repeat=Event.RepeatRule.WEEKLY,
        )
        self.client.login(username="staff-cancel-event", password="testpass")
        response = self.client.post(
            reverse("delete_event_occurrence", kwargs={"event_id": event.pk}),
            {"occurrence_date": "2026-07-08"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(EventCancellation.objects.filter(event=event, occurrence_date=date(2026, 7, 8)).exists())

    def test_non_creator_cannot_delete_single_occurrence(self):
        other = User.objects.create_user(username="other-cancel-event", password="testpass")
        event = Event.objects.create(
            submitted_by=self.member,
            title="Weekly Rehearsal",
            event_date=date(2026, 7, 1),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
            repeat=Event.RepeatRule.WEEKLY,
        )
        self.client.login(username="other-cancel-event", password="testpass")
        response = self.client.post(
            reverse("delete_event_occurrence", kwargs={"event_id": event.pk}),
            {"occurrence_date": "2026-07-08"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(EventCancellation.objects.filter(event=event, occurrence_date=date(2026, 7, 8)).exists())

    def test_single_occurrence_delete_removes_one_time_event(self):
        event = Event.objects.create(
            submitted_by=self.member,
            title="One Time Concert",
            event_date=date(2026, 7, 1),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
            repeat=Event.RepeatRule.NONE,
        )
        self.client.login(username="member", password="testpass")
        response = self.client.post(
            reverse("delete_event_occurrence", kwargs={"event_id": event.pk}),
            {"occurrence_date": "2026-07-01"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Event.objects.filter(pk=event.pk).exists())


class ApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="testpass")
        Post.objects.create(owner=self.owner, title="Hello", body="Members", visibility=Visibility.MEMBERS)
        Post.objects.create(owner=self.owner, title="Public", body="Everyone", visibility=Visibility.PUBLIC)

    def test_home_feed_only_returns_public_posts_for_anonymous_user(self):
        response = self.client.get(reverse("api_home_feed"))
        self.assertEqual(response.status_code, 200)
        titles = [post["title"] for post in response.json()["posts"]]
        self.assertEqual(titles, ["Public"])

    def test_home_feed_returns_member_posts_for_logged_in_user(self):
        self.client.login(username="owner", password="testpass")
        response = self.client.get(reverse("api_home_feed"))
        titles = [post["title"] for post in response.json()["posts"]]
        self.assertIn("Hello", titles)

    def test_home_feed_member_list_excludes_inactive_users(self):
        inactive = User.objects.create_user(username="pending-user", password="testpass", is_active=False)
        inactive.member_profile.display_name = "Pending User"
        inactive.member_profile.save()
        self.client.login(username="owner", password="testpass")
        response = self.client.get(reverse("api_home_feed"))
        member_names = [member["displayName"] for member in response.json()["members"]]
        self.assertIn("owner", member_names)
        self.assertNotIn("Pending User", member_names)

    def test_staff_can_create_pinned_post(self):
        self.owner.is_staff = True
        self.owner.save(update_fields=["is_staff"])
        self.client.login(username="owner", password="testpass")
        response = self.client.post(
            reverse("create_post"),
            {"title": "Pinned", "body": "Stay on top", "visibility": Visibility.MEMBERS, "pinned": "true"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Post.objects.get(title="Pinned").pinned)


    def test_non_staff_cannot_create_pinned_post(self):
        self.client.login(username="owner", password="testpass")
        response = self.client.post(
            reverse("create_post"),
            {"title": "Not pinned", "body": "Regular post", "visibility": Visibility.MEMBERS, "pinned": "true"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertFalse(Post.objects.get(title="Not pinned").pinned)

    def test_pinned_posts_sort_above_regular_posts_with_latest_pinned_first(self):
        first = Post.objects.create(owner=self.owner, title="First pinned", body="One", visibility=Visibility.PUBLIC, pinned=True)
        second = Post.objects.create(owner=self.owner, title="Second pinned", body="Two", visibility=Visibility.PUBLIC, pinned=True)
        regular = Post.objects.create(owner=self.owner, title="Regular", body="Three", visibility=Visibility.PUBLIC)
        Post.objects.filter(pk=first.pk).update(created_at=timezone.now() - timezone.timedelta(days=2))
        Post.objects.filter(pk=second.pk).update(created_at=timezone.now() - timezone.timedelta(days=1))
        Post.objects.filter(pk=regular.pk).update(created_at=timezone.now())
        response = self.client.get(reverse("api_home_feed"))
        titles = [post["title"] for post in response.json()["posts"][:3]]
        self.assertEqual(titles, ["Second pinned", "First pinned", "Regular"])

    def test_owner_can_update_own_post(self):
        post = Post.objects.get(title="Hello")
        self.client.login(username="owner", password="testpass")
        response = self.client.post(
            reverse("update_post", kwargs={"post_id": post.pk}),
            {"title": "Updated", "body": "Revised body", "visibility": Visibility.PUBLIC},
        )
        self.assertEqual(response.status_code, 200)
        post.refresh_from_db()
        self.assertEqual(post.title, "Updated")
        self.assertEqual(post.body, "Revised body")
        self.assertEqual(post.visibility, Visibility.PUBLIC)

    def test_staff_owner_can_update_pinned_state(self):
        self.owner.is_staff = True
        self.owner.save(update_fields=["is_staff"])
        post = Post.objects.get(title="Hello")
        self.client.login(username="owner", password="testpass")
        response = self.client.post(
            reverse("update_post", kwargs={"post_id": post.pk}),
            {"title": "Hello", "body": "Members", "visibility": Visibility.MEMBERS, "pinned": "true"},
        )
        self.assertEqual(response.status_code, 200)
        post.refresh_from_db()
        self.assertTrue(post.pinned)

    def test_non_staff_owner_cannot_update_pinned_state(self):
        post = Post.objects.get(title="Hello")
        self.client.login(username="owner", password="testpass")
        response = self.client.post(
            reverse("update_post", kwargs={"post_id": post.pk}),
            {"title": "Hello", "body": "Members", "visibility": Visibility.MEMBERS, "pinned": "true"},
        )
        self.assertEqual(response.status_code, 200)
        post.refresh_from_db()
        self.assertFalse(post.pinned)

    def test_staff_can_pin_someone_elses_post(self):
        staff = User.objects.create_user(username="staff", password="testpass", is_staff=True)
        post = Post.objects.get(title="Hello")
        self.client.login(username="staff", password="testpass")
        response = self.client.post(reverse("pin_post", kwargs={"post_id": post.pk}), {"pinned": "true"})
        self.assertEqual(response.status_code, 200)
        post.refresh_from_db()
        self.assertTrue(post.pinned)

    def test_staff_can_unpin_someone_elses_post(self):
        staff = User.objects.create_user(username="staff", password="testpass", is_staff=True)
        post = Post.objects.get(title="Hello")
        post.pinned = True
        post.save(update_fields=["pinned"])
        self.client.login(username="staff", password="testpass")
        response = self.client.post(reverse("pin_post", kwargs={"post_id": post.pk}), {"pinned": "false"})
        self.assertEqual(response.status_code, 200)
        post.refresh_from_db()
        self.assertFalse(post.pinned)

    def test_non_staff_cannot_pin_someone_elses_post(self):
        other = User.objects.create_user(username="other-pin", password="testpass")
        post = Post.objects.get(title="Hello")
        self.client.login(username="other-pin", password="testpass")
        response = self.client.post(reverse("pin_post", kwargs={"post_id": post.pk}), {"pinned": "true"})
        self.assertEqual(response.status_code, 403)
        post.refresh_from_db()
        self.assertFalse(post.pinned)

    def test_non_owner_cannot_update_post(self):
        other = User.objects.create_user(username="other", password="testpass")
        post = Post.objects.get(title="Hello")
        self.client.login(username="other", password="testpass")
        response = self.client.post(
            reverse("update_post", kwargs={"post_id": post.pk}),
            {"title": "Bad edit", "body": "Nope", "visibility": Visibility.MEMBERS},
        )
        self.assertEqual(response.status_code, 403)
        post.refresh_from_db()
        self.assertEqual(post.title, "Hello")

    def test_update_post_requires_body(self):
        post = Post.objects.get(title="Hello")
        self.client.login(username="owner", password="testpass")
        response = self.client.post(
            reverse("update_post", kwargs={"post_id": post.pk}),
            {"title": "Updated", "body": "", "visibility": Visibility.MEMBERS},
        )
        self.assertEqual(response.status_code, 400)

    def test_owner_can_delete_own_post(self):
        post = Post.objects.get(title="Hello")
        self.client.login(username="owner", password="testpass")
        response = self.client.post(reverse("delete_post", kwargs={"post_id": post.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Post.objects.filter(pk=post.pk).exists())

    def test_non_owner_cannot_delete_post(self):
        other = User.objects.create_user(username="other-delete", password="testpass")
        post = Post.objects.get(title="Hello")
        self.client.login(username="other-delete", password="testpass")
        response = self.client.post(reverse("delete_post", kwargs={"post_id": post.pk}))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Post.objects.filter(pk=post.pk).exists())

    def test_artifact_upload_requires_file(self):
        self.client.login(username="owner", password="testpass")
        response = self.client.post(reverse("upload_artifact"), {"title": "Score"})
        self.assertEqual(response.status_code, 400)

    def test_create_direct_thread_requires_login(self):
        response = self.client.post(reverse("create_direct_thread"), {"recipient_id": self.owner.pk, "body": "Hello"})
        self.assertEqual(response.status_code, 302)

    def test_create_direct_thread_with_initial_message(self):
        recipient = User.objects.create_user(username="recipient", password="testpass")
        self.client.login(username="owner", password="testpass")
        response = self.client.post(
            reverse("create_direct_thread"),
            {"recipient_id": recipient.pk, "body": "Can you rehearse tonight?"},
        )
        self.assertEqual(response.status_code, 201)
        thread = MessageThread.objects.get(pk=response.json()["thread"]["id"])
        self.assertEqual(thread.participants.count(), 2)
        self.assertEqual(thread.messages.count(), 1)

    def test_thread_detail_limited_to_participants(self):
        recipient = User.objects.create_user(username="recipient", password="testpass")
        outsider = User.objects.create_user(username="outsider", password="testpass")
        thread = MessageThread.objects.create()
        thread.participants.add(self.owner, recipient)
        self.client.login(username="outsider", password="testpass")
        response = self.client.get(reverse("api_thread_detail", kwargs={"thread_id": thread.pk}))
        self.assertEqual(response.status_code, 404)

    def test_thread_page_limited_to_participants(self):
        recipient = User.objects.create_user(username="recipient", password="testpass")
        outsider = User.objects.create_user(username="outsider", password="testpass")
        thread = MessageThread.objects.create()
        thread.participants.add(self.owner, recipient)
        self.client.login(username="outsider", password="testpass")
        response = self.client.get(reverse("thread_page", kwargs={"thread_id": thread.pk}))
        self.assertEqual(response.status_code, 404)

    def test_thread_page_visible_to_participant(self):
        recipient = User.objects.create_user(username="recipient", password="testpass")
        thread = MessageThread.objects.create()
        thread.participants.add(self.owner, recipient)
        self.client.login(username="owner", password="testpass")
        response = self.client.get(reverse("thread_page", kwargs={"thread_id": thread.pk}))
        self.assertEqual(response.status_code, 200)

    def test_send_message_to_thread(self):
        recipient = User.objects.create_user(username="recipient", password="testpass")
        thread = MessageThread.objects.create()
        thread.participants.add(self.owner, recipient)
        self.client.login(username="owner", password="testpass")
        response = self.client.post(reverse("send_message", kwargs={"thread_id": thread.pk}), {"body": "Marked the bowings."})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(thread.messages.count(), 1)


class ArtifactMetadataTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.settings_override = override_settings(
            ARTIFACT_METADATA_HMAC_KEY="artifact-test-key",
            MEDIA_ROOT=self.media_root,
        )
        self.settings_override.enable()
        self.owner = User.objects.create_user(username="artifact-owner", password="testpass")

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.media_root)

    def test_calculate_sha256_streams_uploaded_file(self):
        content = b"guitar ensemble score"
        uploaded_file = SimpleUploadedFile("score.txt", content, content_type="text/plain")

        self.assertEqual(calculate_sha256(uploaded_file), hashlib.sha256(content).hexdigest())
        self.assertEqual(uploaded_file.tell(), 0)

    def test_detect_mime_type_uses_available_detector_or_filename_fallback(self):
        uploaded_file = SimpleUploadedFile("notes.txt", b"plain text", content_type="text/plain")

        self.assertEqual(detect_mime_type(uploaded_file, "notes.txt"), "text/plain")

    def test_metadata_signature_generation_and_verification(self):
        signature = sign_artifact_metadata(
            original_filename="score.pdf",
            stored_filename="artifacts/2026/06/score.pdf",
            mime_type="application/pdf",
            file_size=42,
            sha256_checksum="a" * 64,
        )
        artifact = Artifact(
            original_filename="score.pdf",
            stored_filename="artifacts/2026/06/score.pdf",
            mime_type="application/pdf",
            file_size=42,
            sha256_checksum="a" * 64,
            metadata_signature=signature,
        )

        self.assertEqual(len(signature), 64)
        self.assertTrue(verify_artifact_metadata_signature(artifact))
        self.assertTrue(artifact.verify_metadata_signature())

    def test_metadata_signature_verification_fails_after_checksum_alteration(self):
        signature = sign_artifact_metadata(
            original_filename="score.pdf",
            stored_filename="artifacts/2026/06/score.pdf",
            mime_type="application/pdf",
            file_size=42,
            sha256_checksum="a" * 64,
        )
        artifact = Artifact(
            original_filename="score.pdf",
            stored_filename="artifacts/2026/06/score.pdf",
            mime_type="application/pdf",
            file_size=42,
            sha256_checksum="b" * 64,
            metadata_signature=signature,
        )

        self.assertFalse(verify_artifact_metadata_signature(artifact))

    def test_upload_process_populates_all_metadata(self):
        content = b"%PDF-1.4 test score"
        self.client.login(username="artifact-owner", password="testpass")

        response = self.client.post(
            reverse("upload_artifact"),
            {
                "title": "Etude",
                "description": "Practice score",
                "artifact_type": Artifact.ArtifactType.PDF,
                "visibility": Visibility.MEMBERS,
                "tags": "score,practice",
                "file": SimpleUploadedFile("etude.pdf", content, content_type="application/pdf"),
            },
        )

        self.assertEqual(response.status_code, 201)
        artifact = Artifact.objects.get(title="Etude")
        self.assertEqual(artifact.original_filename, "etude.pdf")
        self.assertTrue(artifact.stored_filename.startswith("artifacts/"))
        self.assertEqual(artifact.file_size, len(content))
        self.assertEqual(artifact.sha256_checksum, hashlib.sha256(content).hexdigest())
        self.assertTrue(artifact.metadata_signature)
        self.assertTrue(artifact.verify_metadata_signature())
        self.assertTrue(artifact.verify_file_integrity())
        self.assertEqual(response.json()["artifact"]["sha256Checksum"], artifact.sha256_checksum)

    def test_duplicate_sha256_values_are_detectable_but_allowed(self):
        checksum = "c" * 64
        first = Artifact.objects.create(
            owner=self.owner,
            title="First",
            file=SimpleUploadedFile("first.txt", b"same"),
            sha256_checksum=checksum,
        )
        second = Artifact.objects.create(
            owner=self.owner,
            title="Second",
            file=SimpleUploadedFile("second.txt", b"same"),
            sha256_checksum=checksum,
        )

        self.assertEqual(Artifact.objects.filter(sha256_checksum=checksum).count(), 2)
        self.assertEqual(list(first.duplicate_artifacts()), [second])

    def test_artifact_search_filters_by_fields_and_links_to_file(self):
        matching = Artifact.objects.create(
            owner=self.owner,
            title="Villa-Lobos Etude",
            description="Score for rehearsal",
            artifact_type=Artifact.ArtifactType.PDF,
            visibility=Visibility.PUBLIC,
            tags="score,etude",
            file="artifacts/villa-lobos.pdf",
            original_filename="villa-lobos.pdf",
            stored_filename="artifacts/villa-lobos.pdf",
            mime_type="application/pdf",
            file_size=128,
            sha256_checksum="d" * 64,
        )
        Artifact.objects.create(
            owner=self.owner,
            title="Audio Reference",
            artifact_type=Artifact.ArtifactType.AUDIO,
            visibility=Visibility.PUBLIC,
            tags="audio",
            file="artifacts/reference.mp3",
            sha256_checksum="e" * 64,
        )

        response = self.client.get(
            reverse("artifact_search"),
            {"title": "Villa", "tags": "etude", "artifact_type": Artifact.ArtifactType.PDF},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, matching.title)
        self.assertContains(response, matching.file.url)
        self.assertNotContains(response, "Audio Reference")

    def test_artifact_search_form_excludes_internal_metadata_fields(self):
        response = self.client.get(reverse("artifact_search"))

        self.assertContains(response, "Title")
        self.assertContains(response, "Description")
        self.assertContains(response, "Tags")
        self.assertNotContains(response, "Artifact ID")
        self.assertNotContains(response, "File path")
        self.assertNotContains(response, "Original filename")
        self.assertNotContains(response, "Stored filename")
        self.assertNotContains(response, "Mime type")
        self.assertNotContains(response, "Minimum file size")
        self.assertNotContains(response, "Maximum file size")
        self.assertNotContains(response, "Sha256 checksum")
        self.assertNotContains(response, "Metadata signature")
        self.assertNotContains(response, "Signature algorithm")

    def test_artifact_search_respects_visibility(self):
        Artifact.objects.create(
            owner=self.owner,
            title="Members Score",
            visibility=Visibility.MEMBERS,
            file="artifacts/members-score.pdf",
            sha256_checksum="f" * 64,
        )

        anonymous_response = self.client.get(reverse("artifact_search"), {"title": "Members"})
        self.assertNotContains(anonymous_response, "Members Score")

        self.client.login(username="artifact-owner", password="testpass")
        member_response = self.client.get(reverse("artifact_search"), {"title": "Members"})
        self.assertContains(member_response, "Members Score")

    def test_artifact_search_paginates_results_at_25(self):
        for index in range(30):
            Artifact.objects.create(
                owner=self.owner,
                title=f"Batch Artifact {index:02d}",
                visibility=Visibility.PUBLIC,
                tags="batch",
                file=f"artifacts/batch-{index:02d}.pdf",
                sha256_checksum=f"{index:064x}"[-64:],
            )

        response = self.client.get(reverse("artifact_search"), {"tags": "batch"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].paginator.count, 30)
        self.assertEqual(len(response.context["page_obj"]), 25)
        self.assertContains(response, "Page 1 of 2")
        self.assertContains(response, "page=2")
