from collections import Counter

from django.utils import timezone

from ..models import Document, InstallationBatch, Site


def status_filter_code(status):
    return {
        Document.Status.APPROVED: "complete",
        Document.Status.UNDER_REVIEW: "review",
        Document.Status.REVISION_REQUIRED: "revision",
        Document.Status.REJECTED: "revision",
        Document.Status.NOT_STARTED: "not-started",
        Document.Status.UPLOADED: "progress",
        Document.Status.DRAFT: "progress",
        Document.Status.NOT_APPLICABLE: "na",
        "PENDING_INSTALLATION": "pending",
    }.get(status, "progress")


def summarize_documents(documents):
    documents = list(documents)
    statuses = {document.status for document in documents}
    if not documents or statuses <= {
        Document.Status.NOT_STARTED,
        Document.Status.NOT_APPLICABLE,
    }:
        return {
            "code": Document.Status.NOT_STARTED,
            "label": "Not Started",
            "filter": "not-started",
        }
    if statuses & {
        Document.Status.REVISION_REQUIRED,
        Document.Status.REJECTED,
    }:
        return {
            "code": Document.Status.REVISION_REQUIRED,
            "label": "Perlu Revisi",
            "filter": "revision",
        }
    if statuses <= {
        Document.Status.APPROVED,
        Document.Status.NOT_APPLICABLE,
    }:
        return {
            "code": Document.Status.APPROVED,
            "label": "Approved",
            "filter": "complete",
        }
    if Document.Status.UNDER_REVIEW in statuses:
        return {
            "code": Document.Status.UNDER_REVIEW,
            "label": "Under Review",
            "filter": "review",
        }
    return {"code": "IN_PROGRESS", "label": "In Progress", "filter": "progress"}


def collect_project_control():
    now = timezone.now()
    sites = list(
        Site.objects.select_related("project").prefetch_related(
            "batches__documents__versions"
        )
    )
    batches = [batch for site in sites for batch in site.batches.all()]
    documents = [
        document
        for batch in batches
        for document in batch.documents.all()
        if document.status != Document.Status.NOT_APPLICABLE
    ]
    counts = Counter(document.status for document in documents)
    approved = counts[Document.Status.APPROVED]
    total_documents = len(documents)

    batch_rows = []
    completed_sites = 0
    revision_sites = 0
    attention = []
    review_aging = []
    missing_files = 0

    for site in sites:
        site_documents = [
            document
            for batch in site.batches.all()
            for document in batch.documents.all()
            if document.status != Document.Status.NOT_APPLICABLE
        ]
        site_summary = summarize_documents(site_documents)
        if site_summary["filter"] == "complete":
            completed_sites += 1
        elif site_summary["filter"] == "revision":
            revision_sites += 1

        for batch in site.batches.all():
            batch_documents = [
                document
                for document in batch.documents.all()
                if document.status != Document.Status.NOT_APPLICABLE
            ]
            by_type = {
                document.document_type: document for document in batch_documents
            }
            approved_count = sum(
                document.status == Document.Status.APPROVED
                for document in batch_documents
            )
            progress = (
                round(approved_count / len(batch_documents) * 100)
                if batch_documents
                else 0
            )
            summary = summarize_documents(batch_documents)
            if batch.status == InstallationBatch.Status.PENDING_INSTALLATION:
                summary = {
                    "code": "PENDING_INSTALLATION",
                    "label": "Pending Instalasi",
                    "filter": "pending",
                }
            batch_rows.append(
                {
                    "batch": batch,
                    "site": site,
                    "qc": by_type.get(Document.Type.QC),
                    "atp": by_type.get(Document.Type.ATP),
                    "fatp": by_type.get(Document.Type.FATP),
                    "qc_filter": status_filter_code(
                        by_type[Document.Type.QC].status
                        if by_type.get(Document.Type.QC)
                        else Document.Status.NOT_STARTED
                    ),
                    "atp_filter": status_filter_code(
                        by_type[Document.Type.ATP].status
                        if by_type.get(Document.Type.ATP)
                        else Document.Status.NOT_STARTED
                    ),
                    "fatp_filter": status_filter_code(
                        by_type[Document.Type.FATP].status
                        if by_type.get(Document.Type.FATP)
                        else Document.Status.NOT_STARTED
                    ),
                    "approved": approved_count,
                    "total": len(batch_documents),
                    "progress": progress,
                    "summary": summary,
                    "last_updated": max(
                        (document.updated_at for document in batch_documents),
                        default=batch.updated_at,
                    ),
                }
            )

            if batch.status == InstallationBatch.Status.PENDING_INSTALLATION:
                attention.append(
                    {
                        "priority": 25,
                        "style": "neutral",
                        "title": f"{site.name} - {batch.label}",
                        "detail": "Instalasi masih pending",
                        "age": "Belum dapat upload",
                        "url_name": "batch_detail",
                        "url_pk": batch.pk,
                    }
                )

            for document in batch_documents:
                has_file = any(version.has_file for version in document.versions.all())
                if not has_file:
                    missing_files += 1
                base = {
                    "title": f"{site.name} - {document.document_type}",
                    "url_name": "document_detail",
                    "url_pk": document.pk,
                }
                if document.status in {
                    Document.Status.REVISION_REQUIRED,
                    Document.Status.REJECTED,
                }:
                    attention.append(
                        {
                            **base,
                            "priority": 100,
                            "style": "danger",
                            "detail": f"{batch.label} - Perlu revisi",
                            "age": "Tindak lanjut",
                        }
                    )
                elif document.status == Document.Status.UNDER_REVIEW:
                    age_days = max(
                        0,
                        (now - (document.submitted_at or document.updated_at)).days,
                    )
                    age_style = (
                        "danger" if age_days >= 5 else "warning" if age_days >= 3 else "info"
                    )
                    review_aging.append(
                        {
                            **base,
                            "batch": batch.label,
                            "days": age_days,
                            "style": age_style,
                        }
                    )
                    attention.append(
                        {
                            **base,
                            "priority": 90 if age_days >= 5 else 60,
                            "style": age_style,
                            "detail": f"{batch.label} - Menunggu review",
                            "age": f"{age_days} hari",
                        }
                    )
                elif (
                    document.status == Document.Status.NOT_STARTED
                    and batch.status != InstallationBatch.Status.PENDING_INSTALLATION
                ):
                    attention.append(
                        {
                            **base,
                            "priority": 40,
                            "style": "neutral",
                            "detail": f"{batch.label} - Belum upload",
                            "age": "Not Started",
                        }
                    )
                elif not has_file and document.status == Document.Status.APPROVED:
                    attention.append(
                        {
                            **base,
                            "priority": 75,
                            "style": "warning",
                            "detail": f"{batch.label} - Approved tanpa file",
                            "age": "Lengkapi file",
                        }
                    )

    review_aging.sort(key=lambda item: item["days"], reverse=True)
    attention.sort(key=lambda item: item["priority"], reverse=True)

    status_breakdown = []
    breakdown_items = (
        ("Approved", approved, "approved"),
        ("Under Review", counts[Document.Status.UNDER_REVIEW], "review"),
        (
            "Perlu Revisi",
            counts[Document.Status.REVISION_REQUIRED]
            + counts[Document.Status.REJECTED],
            "revision",
        ),
        (
            "Proses / Belum Mulai",
            total_documents
            - approved
            - counts[Document.Status.UNDER_REVIEW]
            - counts[Document.Status.REVISION_REQUIRED]
            - counts[Document.Status.REJECTED],
            "pending",
        ),
    )
    for label, count, style in breakdown_items:
        status_breakdown.append(
            {
                "label": label,
                "count": count,
                "style": style,
                "percentage": round(count / total_documents * 100)
                if total_documents
                else 0,
            }
        )

    type_summary = []
    for doc_type, label in Document.Type.choices:
        subset = [
            document for document in documents if document.document_type == doc_type
        ]
        type_approved = sum(
            document.status == Document.Status.APPROVED for document in subset
        )
        type_summary.append(
            {
                "type": label,
                "total": len(subset),
                "approved": type_approved,
                "under_review": sum(
                    document.status == Document.Status.UNDER_REVIEW
                    for document in subset
                ),
                "revision": sum(
                    document.status
                    in {
                        Document.Status.REVISION_REQUIRED,
                        Document.Status.REJECTED,
                    }
                    for document in subset
                ),
                "progress": round(type_approved / len(subset) * 100)
                if subset
                else 0,
            }
        )

    metrics = {
        "sites": len(sites),
        "batches": len(batches),
        "documents": total_documents,
        "approved": approved,
        "sites_completed": completed_sites,
        "sites_revision": revision_sites,
        "sites_pending": len(sites) - completed_sites - revision_sites,
        "under_review": counts[Document.Status.UNDER_REVIEW],
        "revision_required": counts[Document.Status.REVISION_REQUIRED]
        + counts[Document.Status.REJECTED],
        "not_started": counts[Document.Status.NOT_STARTED],
        "pending_installation": sum(
            batch.status == InstallationBatch.Status.PENDING_INSTALLATION
            for batch in batches
        ),
        "overdue_review": sum(item["days"] >= 5 for item in review_aging),
        "missing_files": missing_files,
        "progress": round(approved / total_documents * 100)
        if total_documents
        else 0,
    }
    return {
        "generated_at": timezone.localtime(),
        "metrics": metrics,
        "status_breakdown": status_breakdown,
        "type_summary": type_summary,
        "batch_rows": batch_rows,
        "attention": attention[:12],
        "review_aging": review_aging[:8],
        "pic_options": sorted(
            {batch.pic_name for batch in batches if batch.pic_name.strip()}
        ),
    }
