from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from .models import Article
from appointments.kafka import publish_event

def article_list(request):
    qs = Article.objects.select_related("author").all()

    q = (request.GET.get("q") or "").strip()
    cat = (request.GET.get("cat") or "").strip()

    if q:
        qs = qs.filter(title__icontains=q)
    if cat:
        qs = qs.filter(category=cat)

    categories = Article.CATEGORY_CHOICES

    return render(request, "articles/article_list.html", {
        "articles": qs,
        "q": q,
        "cat": cat,
        "categories": categories,
    })

def _doctor_required(user):
    return user.is_authenticated and user.is_staff

@login_required
def article_create(request):
    if not request.user.is_staff:
        return HttpResponseForbidden("Only doctors can add articles.")

    if request.method == "GET":
        return render(request, "articles/article_form.html", {"mode": "create", "categories": Article.CATEGORY_CHOICES})

    title = (request.POST.get("title") or "").strip()
    category = (request.POST.get("category") or "other").strip()
    summary = (request.POST.get("summary") or "").strip()
    pdf = request.FILES.get("pdf")

    if not title:
        messages.error(request, "Title is required.")
        return redirect("articles:add")

    Article.objects.create(
        title=title,
        category=category,
        summary=summary,
        pdf=pdf,
        author=request.user,
    )

#kafka event
    publish_event(
    "article_created",
    {
        "article_id": article.id,
        "title": article.title,
        "category": article.category,
        "author_id": article.author_id,
        "author_username": request.user.username,
        "pdf_url": article.pdf.url if article.pdf else None,
        "created_at": article.created_at.isoformat(),
    }
    )

    messages.success(request, "Article added.")
    return redirect("articles:list")

@login_required
def article_edit(request, pk: int):
    if not request.user.is_staff:
        return HttpResponseForbidden("Only doctors can edit articles.")

    article = get_object_or_404(Article, pk=pk)

    if article.author_id != request.user.id:
        return HttpResponseForbidden("You can only edit your own articles.")

    if request.method == "GET":
        return render(request, "articles/article_form.html", {
            "mode": "edit",
            "article": article,
            "categories": Article.CATEGORY_CHOICES
        })

    article.title = (request.POST.get("title") or "").strip()
    article.category = (request.POST.get("category") or "other").strip()
    article.summary = (request.POST.get("summary") or "").strip()

    new_pdf = request.FILES.get("pdf")
    if new_pdf:
        article.pdf = new_pdf

    if not article.title:
        messages.error(request, "Title is required.")
        return redirect("articles:edit", pk=article.pk)

    article.save()

    publish_event(
    "article_updated",
    {
        "article_id": article.id,
        "title": article.title,
        "category": article.category,
        "author_id": article.author_id,
        "author_username": request.user.username,
        "pdf_url": article.pdf.url if article.pdf else None,
        "updated_at": article.updated_at.isoformat(),
    }
)

    messages.success(request, "Article updated.")
    return redirect("articles:list")

@login_required
def article_delete(request, pk: int):
    if not request.user.is_staff:
        return HttpResponseForbidden("Only doctors can delete articles.")

    article = get_object_or_404(Article, pk=pk)

    if article.author_id != request.user.id:
        return HttpResponseForbidden("You can only delete your own articles.")

    if request.method != "POST":
        return redirect("articles:list")

    article.delete()

    publish_event(
    "article_deleted",
    {
        "article_id": article.id,
        "title": article.title,
        "author_id": article.author_id,
        "author_username": request.user.username,
    }
)


    messages.success(request, "Article deleted.")
    return redirect("articles:list")
