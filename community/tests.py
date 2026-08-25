import hashlib
import shutil
import tempfile
from django.core import mail
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

    def test_member_drive_link_is_members_only(self):
        drive_url = "https://drive.google.com/drive/folders/10oCU2RxICXlfNexRhz3QFMleLPgUf1N2?usp=sharing"

        anonymous_response = self.client.get(reverse("about"))
        self.assertNotContains(anonymous_response, drive_url)

        User.objects.create_user(username="member", password="testpass")
        self.client.login(username="member", password="testpass")
        member_response = self.client.get(reverse("home"))
        self.assertContains(member_response, drive_url)
        self.assertContains(member_response, "Google Drive")
        self.assertNotContains(member_response, "Member Drive")

    def test_member_home_nav_hides_home_and_orders_links(self):
        User.objects.create_user(username="member", password="testpass")
        self.client.login(username="member", password="testpass")

        response = self.client.get(reverse("home"))
        content = response.content.decode()
        nav_start = content.index('<nav class="top-nav"')
        nav_end = content.index("</nav>", nav_start)
        nav = content[nav_start:nav_end]

        self.assertNotIn(">Home</a>", nav)
        expected_order = ["Members", "Events", "Calendar", "Artifacts", "Google Drive", "Contact", "About", "Logout"]
        positions = [nav.index(label) for label in expected_order]
        self.assertEqual(positions, sorted(positions))

    def test_admin_nav_link_is_only_visible_to_admin_users(self):
        User.objects.create_user(username="member", password="testpass")
        self.client.login(username="member", password="testpass")
        member_response = self.client.get(reverse("home"))
        self.assertNotContains(member_response, 'href="/admin/"')
        self.client.logout()

        User.objects.create_user(username="staff", password="testpass", is_staff=True)
        self.client.login(username="staff", password="testpass")
        staff_response = self.client.get(reverse("home"))
        self.assertContains(staff_response, 'class="admin-nav-link" href="/admin/"')
        self.assertContains(staff_response, "Admin")
        self.client.logout()

        User.objects.create_user(username="superuser", password="testpass", is_superuser=True)
        self.client.login(username="superuser", password="testpass")
        superuser_response = self.client.get(reverse("home"))
        self.assertContains(superuser_response, 'class="admin-nav-link" href="/admin/"')

    @override_settings(CF_TURNSTILE_ENABLED=False)
    def test_signup_creates_inactive_user_when_turnstile_disabled(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "prospective",
                "email": "prospective@example.com",
                "password1": "safe-test-pass-123",
                "password2": "safe-test-pass-123",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Account Awaiting Approval")
        user = User.objects.get(username="prospective")
        self.assertFalse(user.is_active)
        self.assertEqual(user.email, "prospective@example.com")
        self.assertFalse(self.client.login(username="prospective", password="safe-test-pass-123"))

    @override_settings(CF_TURNSTILE_ENABLED=False)
    def test_signup_requires_email(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "prospective",
                "password1": "safe-test-pass-123",
                "password2": "safe-test-pass-123",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required.")
        self.assertFalse(User.objects.filter(username="prospective").exists())

    @override_settings(
        CF_TURNSTILE_ENABLED=False,
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="Radiantensemble.com Admin <mcarroll@radiantensemble.com>",
        SERVER_EMAIL="mcarroll@radiantensemble.com",
        ADMIN_SIGNUP_NOTIFICATION_EMAIL="musicarroll@gmail.com",
    )
    def test_signup_notifies_admin(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "prospective",
                "email": "prospective@example.com",
                "password1": "safe-test-pass-123",
                "password2": "safe-test-pass-123",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, "Radiant Ensemble new user signup")
        self.assertIn("prospective", message.body)
        self.assertIn("awaiting approval", message.body)
        self.assertIn("musicarroll@gmail.com", message.to)
        self.assertEqual(message.bcc, [])

    @override_settings(CF_TURNSTILE_ENABLED=True, CF_TURNSTILE_SECRET_KEY="")
    def test_signup_requires_turnstile_configuration_when_enabled(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "prospective",
                "email": "prospective@example.com",
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

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="Radiantensemble.com Admin <mcarroll@radiantensemble.com>",
        SERVER_EMAIL="mcarroll@radiantensemble.com",
    )
    def test_event_create_edit_and_delete_send_notifications(self):
        recipient = User.objects.create_user(username="event-recipient", password="testpass", email="event@example.com")
        self.client.login(username="member", password="testpass")

        create_response = self.client.post(
            reverse("add_event"),
            {
                "title": "Notification Rehearsal",
                "description": "Bring folders.",
                "location": "Studio A",
                "event_date": "2026-07-10",
                "event_time": "19:30",
                "visibility": Event.EventVisibility.MEMBERS,
                "repeat": Event.RepeatRule.NONE,
            },
        )
        event = Event.objects.get(title="Notification Rehearsal")

        self.assertEqual(create_response.status_code, 302)
        self.assertEqual(mail.outbox[-1].subject, "Radiant Ensemble event created")
        self.assertIn("Notification Rehearsal", mail.outbox[-1].body)
        self.assertIn(reverse("event_detail", kwargs={"event_id": event.pk}), mail.outbox[-1].body)
        self.assertIn(f"{reverse('calendar')}?year=2026&month=7", mail.outbox[-1].body)
        self.assertIn(recipient.email, mail.outbox[-1].bcc)

        edit_response = self.client.post(
            reverse("edit_event", kwargs={"event_id": event.pk}),
            {
                "title": "Updated Notification Rehearsal",
                "description": "Bring pencils.",
                "location": "Studio B",
                "event_date": "2026-07-11",
                "event_time": "20:00",
                "visibility": Event.EventVisibility.PUBLIC,
                "repeat": Event.RepeatRule.WEEKLY,
            },
        )
        event.refresh_from_db()

        self.assertEqual(edit_response.status_code, 302)
        self.assertEqual(mail.outbox[-1].subject, "Radiant Ensemble event updated")
        self.assertIn("Updated Notification Rehearsal", mail.outbox[-1].body)
        self.assertIn(reverse("event_detail", kwargs={"event_id": event.pk}), mail.outbox[-1].body)
        self.assertIn(f"{reverse('calendar')}?year=2026&month=7", mail.outbox[-1].body)

        delete_response = self.client.post(reverse("delete_event", kwargs={"event_id": event.pk}))

        self.assertEqual(delete_response.status_code, 302)
        self.assertEqual(mail.outbox[-1].subject, "Radiant Ensemble event deleted")
        self.assertIn("Updated Notification Rehearsal", mail.outbox[-1].body)
        self.assertIn(f"{reverse('calendar')}?year=2026&month=7", mail.outbox[-1].body)

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

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="Radiantensemble.com Admin <mcarroll@radiantensemble.com>",
        SERVER_EMAIL="mcarroll@radiantensemble.com",
    )
    def test_delete_repeated_occurrence_sends_notification_once(self):
        User.objects.create_user(username="event-recipient", password="testpass", email="event@example.com")
        event = Event.objects.create(
            submitted_by=self.member,
            title="Weekly Notified Rehearsal",
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
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, "Radiant Ensemble event occurrence deleted")
        self.assertIn("Weekly Notified Rehearsal", message.body)
        self.assertIn("Removed occurrence: 2026-07-08", message.body)
        self.assertIn(f"{reverse('calendar')}?year=2026&month=7", message.body)

        duplicate_response = self.client.post(
            reverse("delete_event_occurrence", kwargs={"event_id": event.pk}),
            {"occurrence_date": "2026-07-08"},
        )

        self.assertEqual(duplicate_response.status_code, 404)
        self.assertEqual(len(mail.outbox), 1)

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
        self.owner = User.objects.create_user(username="owner", password="testpass", email="owner@example.com")
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

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="Radiantensemble.com Admin <mcarroll@radiantensemble.com>",
        SERVER_EMAIL="mcarroll@radiantensemble.com",
    )
    def test_create_post_notifies_active_users(self):
        member = User.objects.create_user(
            username="member-with-profile-email",
            password="testpass",
        )
        member.member_profile.email = "profile-member@example.com"
        member.member_profile.save(update_fields=["email"])
        inactive = User.objects.create_user(
            username="inactive-email",
            password="testpass",
            email="inactive@example.com",
            is_active=False,
        )
        self.client.login(username="owner", password="testpass")

        response = self.client.post(
            reverse("create_post"),
            {"title": "Rehearsal notes", "body": "Bring the new score.", "visibility": Visibility.MEMBERS},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, "Radiant Ensemble new home post")
        self.assertIn("owner", message.body)
        self.assertIn("Rehearsal notes", message.body)
        self.assertIn("Bring the new score.", message.body)
        self.assertIn(self.owner.email, message.bcc)
        self.assertIn("profile-member@example.com", message.bcc)
        self.assertNotIn(inactive.email, message.bcc)


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

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="Radiantensemble.com Admin <mcarroll@radiantensemble.com>",
        SERVER_EMAIL="mcarroll@radiantensemble.com",
    )
    def test_create_direct_thread_initial_message_notifies_recipient_only(self):
        recipient = User.objects.create_user(username="recipient", password="testpass", email="recipient@example.com")
        self.client.login(username="owner", password="testpass")

        response = self.client.post(
            reverse("create_direct_thread"),
            {"recipient_id": recipient.pk, "body": "Can you rehearse tonight?"},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, "Radiant Ensemble new direct message")
        self.assertIn("owner", message.body)
        self.assertIn("Can you rehearse tonight?", message.body)
        self.assertIn(recipient.email, message.bcc)
        self.assertNotIn(self.owner.email, message.bcc)

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

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="Radiantensemble.com Admin <mcarroll@radiantensemble.com>",
        SERVER_EMAIL="mcarroll@radiantensemble.com",
    )
    def test_send_message_notifies_all_other_thread_participants(self):
        recipient = User.objects.create_user(username="recipient", password="testpass", email="recipient@example.com")
        profile_recipient = User.objects.create_user(username="profile-recipient", password="testpass")
        profile_recipient.member_profile.email = "profile-recipient@example.com"
        profile_recipient.member_profile.save(update_fields=["email"])
        inactive = User.objects.create_user(
            username="inactive-recipient",
            password="testpass",
            email="inactive@example.com",
            is_active=False,
        )
        thread = MessageThread.objects.create(title="Section chat", is_group_thread=True)
        thread.participants.add(self.owner, recipient, profile_recipient, inactive)
        self.client.login(username="owner", password="testpass")

        response = self.client.post(reverse("send_message", kwargs={"thread_id": thread.pk}), {"body": "Marked the bowings."})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, "Radiant Ensemble new direct message")
        self.assertIn("Section chat", message.body)
        self.assertIn("Marked the bowings.", message.body)
        self.assertIn(recipient.email, message.bcc)
        self.assertIn("profile-recipient@example.com", message.bcc)
        self.assertNotIn(self.owner.email, message.bcc)
        self.assertNotIn(inactive.email, message.bcc)


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

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="Radiantensemble.com Admin <mcarroll@radiantensemble.com>",
        SERVER_EMAIL="mcarroll@radiantensemble.com",
    )
    def test_artifact_upload_notifies_visible_active_users(self):
        self.owner.email = "artifact-owner@example.com"
        self.owner.save(update_fields=["email"])
        recipient = User.objects.create_user(username="artifact-recipient", password="testpass", email="artifact@example.com")
        inactive = User.objects.create_user(
            username="inactive-artifact-recipient",
            password="testpass",
            email="inactive-artifact@example.com",
            is_active=False,
        )
        self.client.login(username="artifact-owner", password="testpass")

        response = self.client.post(
            reverse("upload_artifact"),
            {
                "title": "Notification Etude",
                "description": "Practice score",
                "artifact_type": Artifact.ArtifactType.PDF,
                "visibility": Visibility.MEMBERS,
                "tags": "score,practice",
                "file": SimpleUploadedFile("notification-etude.pdf", b"score", content_type="application/pdf"),
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, "Radiant Ensemble artifact uploaded")
        self.assertIn("Notification Etude", message.body)
        self.assertIn("Practice score", message.body)
        self.assertIn(reverse("artifacts"), message.body)
        self.assertIn(reverse("artifact_search"), message.body)
        self.assertIn(self.owner.email, message.bcc)
        self.assertIn(recipient.email, message.bcc)
        self.assertNotIn(inactive.email, message.bcc)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="Radiantensemble.com Admin <mcarroll@radiantensemble.com>",
        SERVER_EMAIL="mcarroll@radiantensemble.com",
    )
    def test_artifact_update_notifies_visible_active_users(self):
        self.owner.email = "artifact-owner@example.com"
        self.owner.save(update_fields=["email"])
        recipient = User.objects.create_user(username="artifact-recipient", password="testpass", email="artifact@example.com")
        self.client.login(username="artifact-owner", password="testpass")
        upload_response = self.client.post(
            reverse("upload_artifact"),
            {
                "title": "Original Notification Artifact",
                "visibility": Visibility.MEMBERS,
                "file": SimpleUploadedFile("notes.txt", b"notes", content_type="text/plain"),
            },
        )
        artifact = Artifact.objects.get(pk=upload_response.json()["artifact"]["id"])
        mail.outbox.clear()

        response = self.client.post(
            reverse("update_artifact", args=[artifact.pk]),
            {
                "title": "Updated Notification Artifact",
                "description": "Updated artifact details",
                "artifact_type": Artifact.ArtifactType.AUDIO,
                "visibility": Visibility.MEMBERS,
                "tags": "updated",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, "Radiant Ensemble artifact updated")
        self.assertIn("Updated Notification Artifact", message.body)
        self.assertIn("Updated artifact details", message.body)
        self.assertIn(reverse("artifacts"), message.body)
        self.assertIn(reverse("artifact_search"), message.body)
        self.assertIn(self.owner.email, message.bcc)
        self.assertIn(recipient.email, message.bcc)

    def test_owner_can_replace_artifact_file_without_changing_manual_metadata(self):
        original_content = b"original score"
        replacement_content = b"replacement score"
        self.client.login(username="artifact-owner", password="testpass")
        upload_response = self.client.post(
            reverse("upload_artifact"),
            {
                "title": "Etude",
                "description": "Practice score",
                "artifact_type": Artifact.ArtifactType.PDF,
                "visibility": Visibility.MEMBERS,
                "tags": "score,practice",
                "file": SimpleUploadedFile("etude.pdf", original_content, content_type="application/pdf"),
            },
        )
        artifact = Artifact.objects.get(pk=upload_response.json()["artifact"]["id"])
        original_stored_filename = artifact.stored_filename

        response = self.client.post(
            reverse("update_artifact", args=[artifact.pk]),
            {"file": SimpleUploadedFile("etude-v2.txt", replacement_content, content_type="text/plain")},
        )

        self.assertEqual(response.status_code, 200)
        artifact.refresh_from_db()
        self.assertEqual(artifact.title, "Etude")
        self.assertEqual(artifact.description, "Practice score")
        self.assertEqual(artifact.artifact_type, Artifact.ArtifactType.PDF)
        self.assertEqual(artifact.visibility, Visibility.MEMBERS)
        self.assertEqual(artifact.tags, "score,practice")
        self.assertEqual(artifact.original_filename, "etude-v2.txt")
        self.assertEqual(artifact.stored_filename, original_stored_filename)
        self.assertEqual(artifact.file_size, len(replacement_content))
        self.assertEqual(artifact.sha256_checksum, hashlib.sha256(replacement_content).hexdigest())
        self.assertTrue(artifact.verify_metadata_signature())
        self.assertTrue(artifact.verify_file_integrity())
        with artifact.file.open("rb") as file_obj:
            self.assertEqual(file_obj.read(), replacement_content)

    def test_owner_can_update_artifact_manual_metadata_without_replacing_file(self):
        self.client.login(username="artifact-owner", password="testpass")
        upload_response = self.client.post(
            reverse("upload_artifact"),
            {
                "title": "Original",
                "description": "Original description",
                "artifact_type": Artifact.ArtifactType.OTHER,
                "visibility": Visibility.MEMBERS,
                "tags": "old",
                "file": SimpleUploadedFile("notes.txt", b"notes", content_type="text/plain"),
            },
        )
        artifact = Artifact.objects.get(pk=upload_response.json()["artifact"]["id"])
        original_checksum = artifact.sha256_checksum
        original_signature = artifact.metadata_signature

        response = self.client.post(
            reverse("update_artifact", args=[artifact.pk]),
            {
                "title": "Updated",
                "description": "Updated description",
                "artifact_type": Artifact.ArtifactType.AUDIO,
                "visibility": Visibility.PUBLIC,
                "tags": "new,tags",
            },
        )

        self.assertEqual(response.status_code, 200)
        artifact.refresh_from_db()
        self.assertEqual(artifact.title, "Updated")
        self.assertEqual(artifact.description, "Updated description")
        self.assertEqual(artifact.artifact_type, Artifact.ArtifactType.AUDIO)
        self.assertEqual(artifact.visibility, Visibility.PUBLIC)
        self.assertEqual(artifact.tags, "new,tags")
        self.assertEqual(artifact.sha256_checksum, original_checksum)
        self.assertEqual(artifact.metadata_signature, original_signature)
        self.assertTrue(artifact.verify_metadata_signature())

    def test_non_owner_cannot_update_artifact(self):
        other_user = User.objects.create_user(username="other-artifact-user", password="testpass")
        self.client.login(username="artifact-owner", password="testpass")
        upload_response = self.client.post(
            reverse("upload_artifact"),
            {
                "title": "Owned",
                "file": SimpleUploadedFile("owned.txt", b"owned", content_type="text/plain"),
            },
        )
        artifact = Artifact.objects.get(pk=upload_response.json()["artifact"]["id"])
        original_checksum = artifact.sha256_checksum

        self.client.login(username=other_user.username, password="testpass")
        response = self.client.post(
            reverse("update_artifact", args=[artifact.pk]),
            {"title": "Changed by someone else"},
        )

        self.assertEqual(response.status_code, 403)
        artifact.refresh_from_db()
        self.assertEqual(artifact.title, "Owned")
        self.assertEqual(artifact.sha256_checksum, original_checksum)

    def test_staff_can_update_artifact_owned_by_someone_else(self):
        staff_user = User.objects.create_user(username="artifact-admin", password="testpass", is_staff=True)
        self.client.login(username="artifact-owner", password="testpass")
        upload_response = self.client.post(
            reverse("upload_artifact"),
            {
                "title": "Owned",
                "file": SimpleUploadedFile("owned.txt", b"owned", content_type="text/plain"),
            },
        )
        artifact = Artifact.objects.get(pk=upload_response.json()["artifact"]["id"])

        self.client.login(username=staff_user.username, password="testpass")
        response = self.client.post(reverse("update_artifact", args=[artifact.pk]), {"title": "Admin changed"})

        self.assertEqual(response.status_code, 200)
        artifact.refresh_from_db()
        self.assertEqual(artifact.title, "Admin changed")

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

    def test_artifacts_page_lists_visible_artifacts_at_20_per_page(self):
        self.client.login(username="artifact-owner", password="testpass")
        for index in range(25):
            Artifact.objects.create(
                owner=self.owner,
                title=f"Library Artifact {index:02d}",
                visibility=Visibility.MEMBERS,
                file=f"artifacts/library-{index:02d}.pdf",
                sha256_checksum=f"{index:064x}"[-64:],
            )

        response = self.client.get(reverse("artifacts"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("artifact_search"))
        self.assertContains(response, "#artifact-upload")
        self.assertEqual(response.context["page_obj"].paginator.count, 25)
        self.assertEqual(len(response.context["page_obj"]), 20)
        self.assertContains(response, "Page 1 of 2")
        self.assertContains(response, "page=2")

    def test_artifact_search_paginates_results_at_20(self):
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
        self.assertEqual(len(response.context["page_obj"]), 20)
        self.assertContains(response, "Page 1 of 2")
        self.assertContains(response, "page=2")
