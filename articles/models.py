from django.conf import settings
from django.db import models

class Article(models.Model):
    CATEGORY_CHOICES = [
        ("treatment", "Treatment"),
        ("diagnosis", "Diagnosis"),
        ("nutrition", "Nutrition"),
        ("rehab", "Rehab"),
        ("other", "Other"),
    ]

    title = models.CharField(max_length=200)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default="other")
    summary = models.TextField(blank=True)
    pdf = models.FileField(upload_to="articles_pdfs/", blank=True, null=True)

    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="articles")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
