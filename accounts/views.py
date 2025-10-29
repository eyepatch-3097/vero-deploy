from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render, get_object_or_404
from django.db.models import Count, Max, Q
from .forms import SignupForm, OnboardingForm, TypedPostForm
from .models import Onboarding, User
import os
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from django.utils import timezone
import calendar
from django.http import HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.db import transaction
from .forms import UploadForm, GenerateContentForm, ApproveForm, ImproveForm, ChangeTopicForm, AutoPopulateForm
from .models import Upload, StyleProfile, Onboarding, User, CreditTransaction, ContentItem, ContentVersion, GuidelineSchedule, GuidelinePillar
#from .utils import extract_text_from_file, simple_style_summary, record_credit_change, stub_generate_content, stub_improve_content, stub_change_topic_content
from .ai_client import generate_blog, generate_style_fun_facts, generate_linkedin, improve_content as gpt_improve, change_topic as gpt_change
from .ai_client import analyze_style_profile, generate_meta_from_body, suggest_image_search_term
from django.core.paginator import Paginator
from .utils import record_credit_change, extract_text_from_file, merge_user_inputs_into_profile_json, style_scores_from_profile
from .images import search_images


CREDIT_COSTS = {"BLOG": 6, "LINKEDIN": 2}
IMPROVE_COST = 1
CHANGE_TOPIC_COST = 2


def signup_view(request):
    if request.user.is_authenticated:
        return redirect("post_login_router")
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            # email is already on form; you can enforce unique email in model later
            user.email = form.cleaned_data["email"]
            user.save()
            login(request, user)  # auto-login after signup
            messages.success(request, "Account created. Let’s capture your details.")
            return redirect("post_login_router")
    else:
        form = SignupForm()
    return render(request, "accounts/signup.html", {"form": form})

class EmailPasswordLoginView(LoginView):
    template_name = "accounts/login.html"

@login_required
def post_login_router(request):
    # If onboarding not completed, send to onboarding
    if not request.user.onboarding_completed:
        return redirect("onboarding")
    return redirect("profile")  # later this could go to Dashboard

@login_required
def onboarding_view(request):
    user = request.user
    # Get or create the onboarding instance in-memory (no DB write yet)
    try:
        onboarding = user.onboarding
        exists = True
    except Onboarding.DoesNotExist:
        onboarding = Onboarding(user=user)
        exists = False

    if request.method == "POST":
        form = OnboardingForm(request.POST, instance=onboarding)
        if form.is_valid():
            form.instance.user = user
            onboarding = form.save()  # save/updates onboarding

            # mark onboarding complete
            user.onboarding_completed = True
            user.save(update_fields=["onboarding_completed"])

            # --- NEW: create initial Style Profile if none exists and no uploads yet ---
            has_uploads = Upload.objects.filter(user=user).exists()
            has_profile = StyleProfile.objects.filter(user=user).exists()

            if not has_uploads and not has_profile:
                # Build a seed "corpus" from onboarding answers (only if they exist)
                parts = []
                # NOTE: use your actual field names on Onboarding
                if getattr(onboarding, "author_bio", None):
                    parts.append(onboarding.author_bio)
                if getattr(onboarding, "user_style_self_desc", None):
                    parts.append(onboarding.user_style_self_desc)
                if getattr(onboarding, "writing_style_keywords", None):
                    parts.append(f"Topical keywords: {onboarding.writing_style_keywords}")

                corpus = "\n".join([p for p in parts if (p or "").strip()]).strip()

                if corpus:
                    try:
                        # Let AI analyze this seed corpus
                        # You can pass a hint with keywords if your analyze function supports it
                        summary = analyze_style_profile(
                            corpus[:8000],
                            onboarding_keywords=getattr(onboarding, "writing_style_keywords", "") or ""
                        )
                        # Merge the onboarding values into the profile JSON
                        summary = merge_user_inputs_into_profile_json(summary, onboarding)

                        # Create v1 active style profile
                        StyleProfile.objects.filter(user=user, active=True).update(active=False)
                        StyleProfile.objects.create(
                            user=user,
                            version=1,
                            summary_json=summary,
                            active=True
                        )
                        messages.success(request, "Onboarding saved. Your initial Style Profile has been created from your preferences.")
                    except Exception:
                        # Fail soft: onboarding saved, but profile creation failed
                        messages.warning(request, "Onboarding saved. We couldn’t auto-create a Style Profile right now—please use My Style → Regenerate.")
                else:
                    messages.info(request, "Onboarding saved. Add uploads or type a recent post in My Style to build your Style Profile.")
            else:
                messages.success(request, "Onboarding saved.")

            return redirect("profile")

    else:
        form = OnboardingForm(instance=onboarding if exists else None)

    return render(request, "accounts/onboarding.html", {"form": form})

@login_required
def profile_view(request):
    # basic usage stats
    user = request.user
    usage = {
        "blogs_generated": ContentItem.objects.filter(user=user, type="BLOG").count(),
        "linkedin_generated": ContentItem.objects.filter(user=user, type="LINKEDIN").count(),
        "improvements": ContentVersion.objects.filter(content__user=user, version_no__gt=1).count(),
        "last_action": CreditTransaction.objects.filter(user=user).aggregate(Max("created_at"))["created_at__max"],
    }
    return render(request, "accounts/profile.html", {"usage": usage})


@login_required
@require_POST
def upload_file_view(request):
    form = UploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Upload failed. " + "; ".join([str(e) for e in form.errors.values()]))
        return redirect("my_style")

    up: Upload = form.save(commit=False)
    up.user = request.user
    ext = os.path.splitext(up.file.name.lower())[1]
    up.file_type = "TXT" if ext == ".txt" else "PDF"
    up.bytes = request.FILES["file"].size
    up.save()

    # 1) Extract TEXT from the uploaded file
    with up.file.open("rb") as f:
        extracted = extract_text_from_file(f, up.file_type) or ""
    up.text_extract = extracted
    up.save(update_fields=["text_extract"])

    # 2) Rebuild the style profile from ALL uploads (free)
    corpus = "\n".join(
        Upload.objects.filter(user=request.user).values_list("text_extract", flat=True)
    ).strip()

    if corpus:
        trimmed = corpus[:15000]  # keep token usage under control
        onboarding = getattr(request.user, "onboarding", None)
        keywords = onboarding.writing_style_keywords if onboarding else ""

        # deactivate old profile and bump version
        StyleProfile.objects.filter(user=request.user, active=True).update(active=False)
        latest = StyleProfile.objects.filter(user=request.user).first()
        next_version = 1 + (latest.version if latest else 0)

        summary = analyze_style_profile(trimmed, onboarding_keywords=keywords)
        summary = merge_user_inputs_into_profile_json(summary, onboarding)

        StyleProfile.objects.create(
            user=request.user,
            version=next_version,
            summary_json=summary,
            active=True,
        )
        messages.success(request, f"File uploaded. Style Profile v{next_version} regenerated from your uploads.")
    else:
        messages.warning(request, "File uploaded, but no text could be extracted to update your Style Profile.")

    return redirect("my_style")

@login_required
@require_POST
def delete_upload_view(request, upload_id: int):
    up = get_object_or_404(Upload, id=upload_id, user=request.user)
    up.file.delete(save=False)
    up.delete()
    messages.info(request, "File deleted.")
    return redirect("my_style")

@login_required
@require_POST
@transaction.atomic
def regenerate_style_profile_view(request):
    
    extracts = list(Upload.objects.filter(user=request.user).values_list("text_extract", flat=True))
    corpus = "\n".join(Upload.objects.filter(user=request.user).values_list("text_extract", flat=True))

    # If corpus is short, softly pad with onboarding fields (bio, style, topical keywords)
    onboarding = getattr(request.user, "onboarding", None)
    if onboarding and len(corpus) < 500:
        pad = " ".join(filter(None, [onboarding.bio, onboarding.style_self_desc, onboarding.topical_keywords]))
        corpus = (corpus + "\n" + (pad or "")).strip()

    if not corpus.strip():
        rebuilt = []
        for up in Upload.objects.filter(user=request.user):
            try:
                with up.file.open("rb") as f:
                    txt = extract_text_from_file(f, up.file_type) or ""
                if txt.strip():
                    up.text_extract = txt
                    up.save(update_fields=["text_extract"])
                    rebuilt.append(txt)
            except Exception:
                pass
        corpus = "\n".join(rebuilt)

    if not corpus.strip():
        messages.error(request, "Please upload at least one TXT/PDF with text content.")
        return redirect("my_style")
    
    trimmed = corpus[:15000]

    onboarding = getattr(request.user, "onboarding", None)
    keywords = onboarding.writing_style_keywords if onboarding else ""

    try:
        summary = analyze_style_profile(trimmed, onboarding_keywords=keywords)
        summary = merge_user_inputs_into_profile_json(summary, onboarding)
    except Exception as e:
        messages.error(request, f"Could not analyze style right now. Please try again. ({e.__class__.__name__})")
        return redirect("my_style")
    
    facts = []
    try:
        if len(corpus) >= 400:
            facts = generate_style_fun_facts(summary, corpus)
    except Exception:
        facts = []

    StyleProfile.objects.filter(user=request.user, active=True).update(active=False)
    latest = StyleProfile.objects.filter(user=request.user).order_by("-version").first()
    next_version = 1 + (latest.version if latest else 0)
    
    new_profile = StyleProfile.objects.create(
        user=request.user,
        version=next_version,
        summary_json=summary,
        fun_facts=facts,
        active=True,
    )

    StyleProfile.objects.filter(user=request.user).exclude(id=new_profile.id).update(active=False)

    messages.success(request, f"Style Profile v{next_version} generated from your uploads.")
    return redirect("my_style")

@login_required
def my_style_view(request):
     
    uploads = Upload.objects.filter(user=request.user).order_by("-created_at")

    # Active style profile (single, if any)
    active_profile = StyleProfile.objects.filter(user=request.user, active=True).first()

    # Snapshot scores derived from the stored summary_json
    scores = style_scores_from_profile(active_profile.summary_json) \
    if (active_profile and active_profile.summary_json) else {}
    upload_form = UploadForm()

    # Onboarding form (inline editable preferences)
    onboarding = getattr(request.user, "onboarding", None)
    if onboarding is None:
        onboarding = Onboarding(user=request.user)  # unsaved stub so form renders
    onboarding_form = OnboardingForm(instance=onboarding)

    # Fun facts are persisted on the active profile at version-creation time
    raw_facts = active_profile.fun_facts if (active_profile and active_profile.fun_facts) else []
    # normalize to a list in case an older version saved a string
    if isinstance(raw_facts, str):
        try:
            import json
            parsed = json.loads(raw_facts)
            fun_facts = parsed if isinstance(parsed, list) else []
        except Exception:
            # fallback: split by lines if a plain blob
            fun_facts = [ln.strip(" -•\t") for ln in raw_facts.splitlines() if ln.strip()]
    else:
        fun_facts = list(raw_facts)

    return render(request, "accounts/my_style.html", {
        "uploads": uploads,
        "active_profile": active_profile,
        "scores": scores,
        "upload_form": upload_form,
        "onboarding_form": onboarding_form,
        "fun_facts": fun_facts,
    })

@login_required
def credits_view(request):
    txns = CreditTransaction.objects.filter(user=request.user)
    return render(request, "accounts/credits.html", {
        "balance": request.user.credits,
        "transactions": txns,
    })

@login_required
@require_POST
def mock_add_credits(request):
    # Temporary manual top-up
    record_credit_change(request.user, 10, "TOPUP", "Manual add for testing")
    messages.success(request, "Added 10 credits for testing.")
    return redirect("credits")

@login_required
def generate_view(request):
    active_profile = StyleProfile.objects.filter(user=request.user, active=True).first()
    if not active_profile:
        messages.warning(request, "No active Style Profile found. Please go to My Style and generate one first.")
        return redirect("my_style")

    # Prefill topic via ?prefill= and date via ?date=YYYY-MM-DD
    initial_topic = request.GET.get("prefill") or ""
    prefill_date = request.GET.get("date")
    try:
        initial_date = date.fromisoformat(prefill_date) if prefill_date else date.today()
    except ValueError:
        initial_date = date.today()

    form = GenerateContentForm(request.POST or None, initial={"topic": initial_topic, "target_date": initial_date})

    # Suggest topics for the chosen date based on schedule
    chosen_date = initial_date
    if request.method == "POST" and form.is_valid():
        chosen_date = form.cleaned_data["target_date"]

    # Figure pillar for that weekday
    dow = chosen_date.weekday()
    sched = GuidelineSchedule.objects.filter(user=request.user, day_of_week=dow).first()
    suggestions = []
    pillar_for_day = None
    if sched and sched.pillar:
        pillar_for_day = sched.pillar
        suggestions = suggest_topics_stub(pillar_for_day, active_profile.summary_json, n=3)

    if request.method == "POST" and form.is_valid():
        ctype = form.cleaned_data["type"]
        topic = form.cleaned_data["topic"].strip()
        target_date = form.cleaned_data["target_date"]
        cost = CREDIT_COSTS[ctype]

        if request.user.credits < cost:
            messages.error(request, f"Not enough credits. {ctype} requires {cost} credits.")
            return redirect("credits")
        
        # Make target_date 00:00 in the USER'S timezone (e.g., Asia/Kolkata), then store (Django stores UTC)
        user_tz = ZoneInfo(getattr(request.user, "timezone", "Asia/Kolkata") or "Asia/Kolkata")
        local_midnight = datetime.combine(target_date, datetime.min.time())
        aware_local = timezone.make_aware(local_midnight, user_tz)

        item = ContentItem.objects.create(
            user=request.user,
            type=ctype,
            topic=topic,
            status=ContentItem.STATUS_DRAFT,
            scheduled_for=aware_local,
        )
        if ctype == "BLOG":
            body_md, meta_json = generate_blog(topic, active_profile.summary_json)
        else:
            body_md, meta_json = generate_linkedin(topic, active_profile.summary_json)

        ContentVersion.objects.create(content=item, version_no=1, body_md=body_md, meta_json=meta_json)

        record_credit_change(request.user, -cost, "GEN", f"Generated {ctype} for {target_date.isoformat()} – '{topic}'")
        messages.success(request, f"{ctype.title()} draft for {target_date.isoformat()} created. {cost} credits deducted.")
        return redirect("content_detail", content_id=item.id)

    return render(request, "accounts/generate.html", {
        "form": form,
        "active_profile": active_profile,
        "suggestions": suggestions,
        "pillar_for_day": pillar_for_day,
    })

@login_required
def history_view(request):
    qs = ContentItem.objects.filter(user=request.user).order_by("-created_at")
    # simple filters later; for now paginate
    page = request.GET.get("page", 1)
    items = Paginator(qs, 10).get_page(page)
    return render(request, "accounts/history.html", {"items": items})

@login_required
def content_detail_view(request, content_id: int):
    item = get_object_or_404(ContentItem, id=content_id, user=request.user)
    latest = item.versions.first()  # ordered by -version_no
    image_query = ""
    image_results = []

    if latest and (latest.body_md or item.topic):
        base_q = suggest_image_search_term(latest.body_md or "", item.type, item.topic)
        image_query = (base_q or item.topic or "").strip()
        if image_query:
            image_query = f"{image_query}"
            image_results = search_images(image_query, count=10)

    return render(request, "accounts/content_detail.html", {"item": item, "latest": latest, "image_query": image_query, "image_results": image_results})

@login_required
@require_POST
def approve_content_view(request, content_id: int):
    item = get_object_or_404(ContentItem, id=content_id, user=request.user)
    form = ApproveForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please confirm approval.")
        return redirect("content_detail", content_id=item.id)

    item.status = ContentItem.STATUS_APPROVED
    item.save(update_fields=["status"])
    messages.success(request, "Content approved.")
    return redirect("content_detail", content_id=item.id)

@login_required
@require_POST
def improve_content_view(request, content_id: int):
    item = get_object_or_404(ContentItem, id=content_id, user=request.user)
    latest = item.versions.first()
    if not latest:
        messages.error(request, "No version to improve.")
        return redirect("content_detail", content_id=item.id)

    form = ImproveForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please fix the form errors for Improve.")
        return redirect("content_detail", content_id=item.id)

    if request.user.credits < IMPROVE_COST:
        messages.error(request, f"Not enough credits. Improve requires {IMPROVE_COST} credit.")
        return redirect("credits")

    active_profile = StyleProfile.objects.filter(user=request.user, active=True).first()
    if not active_profile:
        messages.error(request, "No active Style Profile found.")
        return redirect("my_style")

    opts = form.cleaned_data
    new_body, new_meta = gpt_improve(item.type, latest.body_md, active_profile.summary_json, opts)

    REGENERATE = True  # toggle (move to settings if you want)

    meta_for_new_version = (
        generate_meta_from_body(new_body) if (REGENERATE and item.type == "BLOG") else (latest.meta_json or {})
    )

    next_ver = (latest.version_no or 1) + 1
    ContentVersion.objects.create(content=item, version_no=next_ver, body_md=new_body, meta_json=meta_for_new_version)

    record_credit_change(request.user, -IMPROVE_COST, "IMPROVE", f"Improve content v{next_ver} for '{item.topic}'")
    messages.success(request, f"Improved content to v{next_ver}. {IMPROVE_COST} credit deducted.")
    return redirect("content_detail", content_id=item.id)

@login_required
@require_POST
def change_topic_view(request, content_id: int):
    item = get_object_or_404(ContentItem, id=content_id, user=request.user)
    form = ChangeTopicForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please provide a new topic.")
        return redirect("content_detail", content_id=item.id)

    if request.user.credits < CHANGE_TOPIC_COST:
        messages.error(request, f"Not enough credits. Change Topic requires {CHANGE_TOPIC_COST} credits.")
        return redirect("credits")

    active_profile = StyleProfile.objects.filter(user=request.user, active=True).first()
    if not active_profile:
        messages.error(request, "No active Style Profile found.")
        return redirect("my_style")

    new_topic = form.cleaned_data["new_topic"].strip()
    body_md, meta_json = gpt_change(item.type, new_topic, active_profile.summary_json)

    latest = item.versions.first()
    next_ver = (latest.version_no if latest else 0) + 1
    ContentVersion.objects.create(content=item, version_no=next_ver, body_md=body_md, meta_json=meta_json)

    # update item topic
    item.topic = new_topic
    item.status = ContentItem.STATUS_DRAFT
    item.save(update_fields=["topic","status"])

    record_credit_change(request.user, -CHANGE_TOPIC_COST, "GEN", f"Change Topic → '{new_topic}'")
    messages.success(request, f"Topic changed and v{next_ver} created. {CHANGE_TOPIC_COST} credits deducted.")
    return redirect("content_detail", content_id=item.id)

@login_required
def calendar_view(request):
    mode = request.GET.get("mode", "grid")  # "grid" or "list"

    # Accept ?month=YYYY-MM
    month_q = request.GET.get("month")
    today = date.today()
    if month_q:
        try:
            year, mon = map(int, month_q.split("-"))
        except Exception:
            year, mon = today.year, today.month
    else:
        year, mon = today.year, today.month

    cal = calendar.Calendar(firstweekday=0)  # Monday=0
    weeks = cal.monthdatescalendar(year, mon)  # list[list[date]]
    user_tz = ZoneInfo(getattr(request.user, "timezone", "Asia/Kolkata") or "Asia/Kolkata")

    # Range for counts
    _, last_day = calendar.monthrange(year, mon)
    start_local = datetime(year, mon, 1, 0, 0, 0, tzinfo=user_tz)
    end_local_exclusive = datetime(year, mon, last_day, 23, 59, 59, 999999, tzinfo=user_tz) + timedelta(microseconds=1)

    # Convert to UTC for DB filtering
    utc = ZoneInfo("UTC")
    start_utc = start_local.astimezone(utc)
    end_utc = end_local_exclusive.astimezone(utc)

    # Build counts per day keyed by ISO date string
    qs = ContentItem.objects.filter(
        user=request.user,
        scheduled_for__date__gte=start_utc,
        scheduled_for__date__lte=end_utc,
    )
    counts_map, items_map = {}, {}
    for it in qs:
        d = it.scheduled_for.date()
        local_date = it.scheduled_for.astimezone(user_tz).date()
        key = local_date.isoformat()
        if key not in counts_map:
            counts_map[key] = {"BLOG": 0, "LINKEDIN": 0}
        counts_map[key][it.type] += 1
        items_map.setdefault(key, []).append(it)

    day_list = [date(year, mon, d) for d in range(1, last_day + 1)]
    # Prev / next month strings
    first_this_month = date(year, mon, 1)
    prev_first = (first_this_month - timedelta(days=1)).replace(day=1)
    next_month_day1 = (date(year, mon, last_day) + timedelta(days=1)).replace(day=1)

    context = {
        "mode": mode,
        "year": year,
        "month": mon,        # keep as int
        "weeks": weeks,
        "day_list":day_list,
        "counts_map": counts_map,  # dict keyed by 'YYYY-MM-DD'
        "items_map": items_map,
        "prev_month": prev_first.strftime("%Y-%m"),
        "next_month": next_month_day1.strftime("%Y-%m"),
    }
    return render(request, "accounts/calendar.html", context)

@login_required
@require_POST
@transaction.atomic
def auto_populate_view(request):
    form = AutoPopulateForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please fix the Auto-Populate form.")
        return redirect("calendar")

    ctype = form.cleaned_data["content_type"]
    raw = form.cleaned_data["dates"].strip().splitlines()
    dates = []
    for line in raw:
        line = line.strip()
        if not line: continue
        try:
            dates.append(date.fromisoformat(line))
        except ValueError:
            messages.error(request, f"Invalid date: {line}")
            return redirect("calendar")

    if not dates:
        messages.error(request, "Provide at least one date.")
        return redirect("calendar")
    if len(dates) > 7:
        messages.error(request, "Select at most 7 dates at a time.")
        return redirect("calendar")

    active_profile = StyleProfile.objects.filter(user=request.user, active=True).first()
    if not active_profile:
        messages.error(request, "No active Style Profile found. Please create one in My Style.")
        return redirect("my_style")

    COSTS = {"BLOG": 6, "LINKEDIN": 2}
    total_cost = COSTS[ctype] * len(dates)
    if request.user.credits < total_cost:
        messages.error(request, f"Not enough credits. Need {total_cost}, you have {request.user.credits}.")
        return redirect("credits")

    # Timezone-aware scheduling
    user_tz = ZoneInfo(getattr(request.user, "timezone", "Asia/Kolkata") or "Asia/Kolkata")

    created = 0
    for d in dates:
        local_midnight = datetime.combine(d, datetime.min.time())
        aware_local = timezone.make_aware(local_midnight, user_tz)

        topic_seed = None
        # Optional: bias topics by user_topical_keywords if blank topic
        # We’ll generate using the calendar day’s pillar suggestion later if desired.

        # Generate content body/meta
        if ctype == "BLOG":
            body_md, meta_json = generate_blog(topic_seed or f"Idea for {d.isoformat()}", active_profile.summary_json)
        else:
            body_md, meta_json = generate_linkedin(topic_seed or f"Idea for {d.isoformat()}", active_profile.summary_json)

        item = ContentItem.objects.create(
            user=request.user,
            type=ctype,
            topic=meta_json.get("meta_title") or topic_seed or f"{ctype.title()} for {d.isoformat()}",
            status=ContentItem.STATUS_DRAFT,
            scheduled_for=aware_local,
        )
        ContentVersion.objects.create(content=item, version_no=1, body_md=body_md, meta_json=meta_json)
        created += 1

    # Single debit for the batch
    record_credit_change(request.user, -total_cost, "GEN", f"Auto-generate {created} {ctype} items")

    messages.success(request, f"Created {created} {ctype.title()} draft(s). {total_cost} credits deducted.")
    # Bounce back to the month that contains the first selected date
    return redirect(f"/calendar/?month={dates[0].strftime('%Y-%m')}&mode=list")


@login_required
@require_POST
def add_typed_post_view(request):
    form = TypedPostForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please type something to add.")
        return redirect("my_style")

    text = form.cleaned_data["text"].strip()
    if not text:
        messages.error(request, "Text is empty.")
        return redirect("my_style")

    # Save as an Upload of type TEXT
    Upload.objects.create(
        user=request.user,
        file=None,
        file_type="TEXT",
        text_extract=text,
        bytes=len(text.encode("utf-8")),
        # source="TEXT"  # if you added the field
    )

    # Rebuild style profile from ALL uploads + onboarding
    extracts = list(Upload.objects.filter(user=request.user).values_list("text_extract", flat=True))
    corpus = "\n".join([t for t in extracts if (t or "").strip()])[:15000]
    onboarding = getattr(request.user, "onboarding", None)
    keywords = onboarding.writing_style_keywords if onboarding else ""

    if not corpus:
        messages.warning(request, "Saved your text, but couldn’t build a profile (no text found).")
        return redirect("my_style")

    summary = analyze_style_profile(corpus, onboarding_keywords=keywords)
    summary = merge_user_inputs_into_profile_json(summary, onboarding)

    StyleProfile.objects.filter(user=request.user, active=True).update(active=False)
    latest = StyleProfile.objects.filter(user=request.user).order_by("-version").first()
    next_ver = 1 + (latest.version if latest else 0)
    StyleProfile.objects.create(user=request.user, version=next_ver, summary_json=summary, active=True)

    messages.success(request, f"Added your post and generated Style Profile v{next_ver}.")
    return redirect("my_style")

@login_required
@require_POST
@transaction.atomic
def save_onboarding_inline(request):
    onboarding = getattr(request.user, "onboarding", None)
    if onboarding is None:
        onboarding = Onboarding(user=request.user)

    form = OnboardingForm(request.POST, instance=onboarding)
    if not form.is_valid():
        messages.error(request, "Please fix errors in the form.")
        return redirect("my_style")

    # 1) Save updated author preferences
    onboarding = form.save()

    # 2) Build/refresh corpus from uploads
    extracts = list(
        Upload.objects.filter(user=request.user).values_list("text_extract", flat=True)
    )
    corpus = "\n".join([t for t in extracts if (t or "").strip()])

    # Soft pad with onboarding fields if corpus is too short
    if len(corpus) < 500:
        pad = " ".join(filter(None, [onboarding.bio, onboarding.style_self_desc, onboarding.topical_keywords]))
        corpus = (corpus + "\n" + (pad or "")).strip()

    if not corpus.strip():
        # If still nothing to analyze, just mark onboarding saved and return
        messages.success(request, "Preferences saved. Add an upload or a typed post to generate your Style Profile.")
        return redirect("my_style")

    trimmed = corpus[:15000]
    keywords = onboarding.writing_style_keywords or ""

    # 3) Analyze + merge onboarding inputs into the profile JSON
    try:
        summary = analyze_style_profile(trimmed, onboarding_keywords=keywords)
        summary = merge_user_inputs_into_profile_json(summary, onboarding)
    except Exception as e:
        messages.error(request, f"Could not analyze style right now. ({e.__class__.__name__})")
        return redirect("my_style")

    # 4) Generate fun facts on this same path (lower threshold so most users see something)
    facts = []
    try:
        if len(corpus) >= 120:
            facts = generate_style_fun_facts(summary, corpus)
    except Exception:
        facts = []

    # 5) Deactivate old active profile and create a new one with fun_facts
    StyleProfile.objects.filter(user=request.user, active=True).update(active=False)
    latest = StyleProfile.objects.filter(user=request.user).order_by("-version").first()
    next_version = 1 + (latest.version if latest else 0)

    StyleProfile.objects.create(
        user=request.user,
        version=next_version,
        summary_json=summary,
        fun_facts=facts,   # ← ensure fun facts are saved here
        active=True,
    )

    messages.success(request, f"Preferences saved. Style Profile v{next_version} generated.")
    return redirect("my_style")
