# Session Notes

## 2026-06-02

- Started a new Django 5.0 project for `radiantensemble.com` in `/home/mcarroll/Documents/python/radiantensemble/website`.
- Referenced cognotrend.com for its simple top-navigation/content-site structure, while planning Radiant Ensemble around a React-enabled three-panel home view.
- Added the `community` app as the main domain app.
- Configured sqlite3, local/static/media settings, auth redirects, and allowed hosts for localhost plus `radiantensemble.com`.
- Added models for:
  - `MemberProfile` with slugged member pages, theme/color fields, custom CSS, and public-page control.
  - `Post` with owner, pinned flag, and visibility controls.
  - `Artifact` for uploaded musical files including PDFs, audio, images, artwork, tags, and visibility controls.
  - `MessageThread` and `Message` for members-only direct and group messaging foundations.
- Added visibility choices: public, members-only, selected groups, and private. Members-only is the default for posts and artifacts.
- Added Django admin registrations for profiles, posts, artifacts, and message threads.
- Added a profile-creation signal so new Django users automatically receive a member profile.
- Added JSON endpoints for the React home app:
  - `/api/me/`
  - `/api/home-feed/`
  - `/api/artifacts/`
  - `/api/threads/`
  - `/api/posts/`
  - `/api/artifacts/upload/`
- Added Django templates for the base layout, React home mount, member page, and login.
- Added a Vite/React frontend source at `frontend/src/home.jsx` with a Facebook-like three-panel layout:
  - Left rail for members/account state.
  - Center rail for composer and feed.
  - Right rail for private messages and artifacts.
- Added focused Django tests for visibility and API behavior.

## 2026-06-02 Admin Login Troubleshooting

- Confirmed the `mcarroll` superuser exists and has `is_staff=True`, `is_superuser=True`, `is_active=True`, and a usable password.
- Found that the explicit `ALLOWED_HOSTS` list rejected Django's `testserver` host and would reject browser access through `0.0.0.0`.
- Added development host entries for `.localhost`, `0.0.0.0`, and `testserver` while retaining `radiantensemble.com` and `www.radiantensemble.com`.

## 2026-06-02 Artifact Upload Widget

- Added an authenticated React upload form to the right-side Artifacts panel on the home dashboard.
- The widget posts multipart form data to `/api/artifacts/upload/` and refreshes the dashboard after a successful upload.
- Upload fields include title, description, artifact type, visibility, tags, and file.
- Anonymous visitors now see a login prompt instead of upload controls.
- Fixed a React upload-handler bug where `event.currentTarget.reset()` ran after an awaited API call and could fail because React cleared the event target. The handler now stores the form element before awaiting upload.

## 2026-06-02 Direct Messaging Widget

- Added backend endpoints for direct messaging:
  - `/api/threads/create-direct/` to start a one-to-one thread.
  - `/api/threads/<thread_id>/` to fetch a participant-visible thread and its messages.
  - `/api/threads/<thread_id>/messages/` to send a message to an existing thread.
- Message endpoints require login and restrict thread detail/send access to participants.
- Added React messaging controls in the right-side Messages panel:
  - Select a member and start a direct message.
  - Select existing message threads.
  - View conversation messages.
  - Send replies.
- Added tests for login requirements, direct-thread creation, participant-only thread access, and sending messages.

## 2026-06-02 Message Thread Page

- Moved active conversation detail out of the home dashboard and into a dedicated `/messages/<thread_id>/` page.
- The home Messages panel now stays compact:
  - It has a fixed-height scrollable thread list.
  - Existing threads link to their conversation pages.
  - Starting a new direct message redirects to the new thread page.
- Added a separate React entry point at `frontend/src/thread.jsx` and Vite now builds both `home.js` and `thread.js`.
- The conversation page has a fixed viewport-height layout, a scrollable message history, and a fixed reply form area.
- Message history automatically scrolls to the newest message after load and after sending a reply while still allowing manual scrolling to older messages.
- Added tests for participant-only access to the conversation page.

## 2026-06-02 Owner-Only Post Editing

- Added `POST /api/posts/<post_id>/` to update an existing post.
- The member-facing update endpoint allows edits only when `request.user` is the post owner. Non-owners receive `403`.
- Editable fields are title, body, and visibility.
- Added inline React edit controls to feed posts only when the logged-in user owns the post.
- Added tests for owner edit success, non-owner rejection, and required post body validation.

## 2026-06-02 Staff Pinning and Owner Delete

- Added staff-only pinning for member-facing post creation and editing. This uses Django `is_staff` as the current "rank and above" threshold.
- Pinned posts use the existing model ordering, so pinned posts appear above regular posts and newer pinned posts appear above older pinned posts.
- Added a pinned badge in the feed and a "Keep this post on top" checkbox for staff users.
- Added `POST /api/posts/<post_id>/delete/` for owner-only post deletion.
- Added Delete controls inside the owner-only React edit form.
- Added tests for staff pin creation, non-staff pin rejection, pinned ordering, staff pin editing, non-staff pin editing rejection, owner delete, and non-owner delete rejection.
- Added a staff-only moderation endpoint at `/api/posts/<post_id>/pin/` so staff users can pin or unpin posts owned by other members without changing post content.
- Feed post cards now show staff users Pin/Unpin controls on all posts while preserving owner-only Edit/Delete controls.

## 2026-06-02 Linkified Post URLs

- Added React display logic that converts `https://...`, `http://...`, and `www...` URLs in post bodies into live links.
- Post bodies are still stored as plain text and user-entered HTML is not rendered.
- Member profile pages now use Django's `urlize` filter for post bodies.

## 2026-06-02 Public About And Contact Pages

- Added `/about/` as the public-facing alternate home page for unauthenticated visitors.
- Updated `/` so unauthenticated visitors redirect to `/about/`, while authenticated members still see the React dashboard.
- Added `/contact/` with a Django `ContactForm` and `ContactMessage` database model.
- Added Django admin support for reviewing contact messages.
- Added Cloudflare Turnstile support using settings loaded from ignored `.env/config.py`.
- Added `.env.example/config.py` documenting the required Turnstile settings shape.
- Added public navigation links for About and Contact.
- Added `AGENTS.md` with an explicit prohibition on using or recommending `git clean` in this repository.
- Added tests for anonymous home redirect, authenticated home access, About loading, disabled-Turnstile contact submission, and enabled-but-unconfigured Turnstile rejection.

## 2026-06-02 Radiant Graphic Hero

- Copied `/home/mcarroll/Pictures/radiant_graphic.png` into `community/static/community/images/radiant_graphic.png`.
- Updated the public About hero and logged-in React dashboard hero styling to use the Radiant graphic as the background image with an overlay for text readability.
- Revised the About and dashboard heroes to remove overlay text and display the Radiant graphic directly as an image, preserving its original colors and aspect ratio.
- Replaced the static hero image with `/home/mcarroll/Downloads/radiant_guitar.png`, copied over `community/static/community/images/radiant_graphic.png` so existing templates continue to reference the same asset path.

## 2026-06-02 Calendar And Upcoming Events

- Added an `Event` model with title, description, location, date, time, visibility, repeat rule, and submitter.
- Event visibility supports public and members-only.
- Event repeat rules support none, daily, weekly, and monthly.
- Added member-only `/calendar/` month view with previous/next month navigation and usual calendar grid layout.
- Added member-only `/calendar/add/` form so authenticated members can submit events.
- Added public `/events/` Upcoming Events page listing public events on or after the current day in chronological order.
- Recurring public events appear on Upcoming Events using their next occurrence on or after today.
- Added `/events/<event_id>/` details page with visibility checks. Calendar/upcoming links include an occurrence date for repeated events.
- Added navigation links for public Events and member Calendar.
- Added tests for calendar login requirements, event submission, upcoming public visibility, hidden member-only events, event detail visibility, weekly recurrence in the calendar, and recurring public upcoming events.

## 2026-06-03 Monthly Ordinal Weekday Events

- Added a new event repeat option: `Monthly on same ordinal weekday`.
- This supports patterns such as the 1st Sunday, 2nd Tuesday, 3rd Friday, or 4th Monday of each month, derived from the first event date.
- Kept the existing monthly option as "Monthly on same day of month" so existing monthly behavior is unchanged.
- Added tests for ordinal weekday matching, calendar rendering in a later month, and public upcoming event expansion for ordinal monthly repeats.

## 2026-06-03 Event Creator And Staff Management

- Added event editing at `/events/<event_id>/edit/`.
- Added event deletion at `/events/<event_id>/delete/`.
- Event creators can edit or delete events they submitted.
- Staff users can edit or delete any event regardless of submitter.
- Unauthorized event management requests return 404.
- Event details now show Edit/Delete controls only to users who can manage that event.
- Added tests for creator edit/delete, staff edit/delete of another member's events, and non-creator denial.

## 2026-06-06 Single Occurrence Event Deletion

- Added `EventCancellation` model to suppress one occurrence date from a repeated event without deleting the whole event series.
- Added `/events/<event_id>/delete-occurrence/` for event creators and staff users.
- Event detail pages now include both "Delete This Occurrence" and "Delete Series" controls for users who can manage the event.
- For one-time events, deleting the single occurrence deletes the event record.
- Calendar, event detail, and upcoming-events expansion now respect cancelled occurrences.
- Added tests for creator/staff occurrence deletion, non-creator denial, one-time event deletion through the occurrence path, and hiding cancelled dates from the calendar.

## 2026-06-08 Bug Reports And Feature Requests

- Added `BugReport` model with title, description, steps to reproduce, expected behavior, actual behavior, page URL, severity, status, submitter, and timestamps.
- Added `FeatureRequest` model with title, description, use case, benefit, impact, status, submitter, and timestamps.
- Added Django admin registrations for both models so staff can triage status/severity/impact.
- Added member-only pages for bug report list, create, and detail.
- Added member-only pages for feature request list, create, and detail.
- Added authenticated navigation links for Bugs and Features.
- Added tests confirming anonymous users cannot access lists/details, members can submit both types, and details render only for authenticated members.

## 2026-06-08 Member Profile Views And Editing

- Extended `MemberProfile` with profile photo upload, dedicated phone, and dedicated email fields.
- Added `MemberProfileLink` model so members can maintain a list of recommended links with optional descriptions and sort order.
- Added member-only profile list at `/members/`.
- Converted member profile detail pages to member-only access.
- Added `/members/me/edit/` so members can update their own profile photo, bio, phone, email, accent color, and recommended links.
- Added admin inline management for member profile links.
- Added navigation links for Members and My Profile.
- Added tests for member-only profile list/detail access and profile/link editing.

## 2026-06-09 Footer Navigation And Hosting Credit

- Added a shared footer banner to every page: "Designed and hosted by cognotrend.com LLC", with `cognotrend.com` linking to `https://cognotrend.com`.
- Moved Bug Reports, Feature Requests, and Admin links out of the top navigation.
- Revised the home page Account panel to show vertical links for My Profile, Bug Reports, Feature Requests, and Admin, with Admin visible only to staff users.
- Centered the footer hosting credit at the bottom of each page.
- Adjusted the header navigation to wrap cleanly on mobile.
- Reduced the home page Radiant graphic display size to 50% width while leaving the source image unchanged.
- Reduced the About page Radiant graphic display size to 50% width while leaving the source image unchanged.
