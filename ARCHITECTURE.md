# Architecture Blueprint

## Topologi

```mermaid
flowchart TD
    U[Triple E dan Nokia] --> C[Cloudflare Tunnel]
    C --> W[Django DMS :8095]
    W --> P[(PostgreSQL)]
    W --> D[(Local Document Storage)]
    B[Backup scheduler] --> P
    B --> D
```

Cloudflare mengarah ke `http://192.168.100.110:8095`. PostgreSQL hanya berada di private Docker network dan tidak memiliki host port.

## Hierarki data

```mermaid
flowchart TD
    P[Project] --> S[Physical Site]
    S --> B[Installation Batch]
    B --> D[QC / ATP / FATP]
    D --> V[Document Revisions]
    V --> A[File Attachments]
    V --> R[Internal Decisions and Comments]
```

Mentigi dan HUT. Sungai Liat masing-masing mempunyai satu physical site dan satu installation batch. Total terkoreksi adalah 16 physical sites, 16 batches, dan 48 document registers.

## Entity relationship

```mermaid
erDiagram
    PROJECT ||--o{ SITE : contains
    SITE ||--o{ INSTALLATION_BATCH : schedules
    INSTALLATION_BATCH ||--|{ DOCUMENT : requires
    DOCUMENT ||--o{ DOCUMENT_VERSION : versions
    DOCUMENT_VERSION ||--|{ DOCUMENT_ATTACHMENT : files
    DOCUMENT ||--o{ REVIEW : reviewed
    DOCUMENT ||--o{ DOCUMENT_COMMENT : discusses
    USER ||--o{ DOCUMENT_VERSION : uploads
    USER ||--o{ REVIEW : decides
    USER ||--o{ ACTIVITY_LOG : performs
    USER ||--o{ NOTIFICATION : receives
```

## Source of truth

| Informasi | Source of truth |
|---|---|
| Site, batch, status, role | PostgreSQL |
| Review, komentar, notifikasi | PostgreSQL |
| Audit upload/preview/download | PostgreSQL |
| File dokumen dan backup | Storage lokal server CasaOS |
| Storage key, checksum, revision number | PostgreSQL |

## Document state machine

```mermaid
stateDiagram-v2
    [*] --> NotStarted
    NotStarted --> Uploaded: Triple E uploads
    NotStarted --> UnderReview: Upload and submit
    NotStarted --> Approved: Super Admin uploads signed file
    Uploaded --> UnderReview: Submit to Nokia
    Uploaded --> Approved: Super Admin uploads signed file
    UnderReview --> Approved: Super Admin finalizes
    UnderReview --> Approved: Upload signed revision
    UnderReview --> RevisionRequired: Super Admin requests revision
    UnderReview --> Rejected: Super Admin rejects internally
    RevisionRequired --> Uploaded: Upload next revision
    Rejected --> Uploaded: Upload corrected revision
    Approved --> RevisionRequired: Admin reopens with reason
```

Approved versions remain immutable. Reopening a document changes the register status but never deletes or overwrites the approved file.

## Role matrix

| Role | View/download | Upload/submit | Review decision | User admin | Reopen approved |
|---|:---:|:---:|:---:|:---:|:---:|
| Super Admin | Ya | Ya, termasuk Signed/TTD | Ya, termasuk direct Approved | Semua role | Ya |
| Triple E Admin | Ya | Ya | Tidak | Selain Super Admin | Ya |
| Triple E Engineer | Ya | Ya | Tidak | Tidak | Tidak |
| Nokia Reviewer | Ya | Tidak | Tidak; komentar saja | Tidak | Tidak |
| Nokia Viewer | Ya | Tidak | Tidak | Tidak | Tidak |

Semua role dapat menambahkan komentar. Nokia mengakses file melalui endpoint DMS terautentikasi, tetapi tidak dapat menetapkan Approve, Reject, atau Request Revision. Keputusan status hanya tersedia untuk Super Admin.

Form upload menyediakan tiga aksi. Draft menyimpan file tanpa mengunci revisi, Submit Review
langsung mengubah status menjadi Under Review, sedangkan Signed/TTD mengubah status menjadi
Approved dan hanya dapat digunakan oleh Super Admin. Semua aksi tercatat di audit trail.

## Security boundaries

- Folder dokumen hanya di-mount ke container web dan tidak dipublikasikan sebagai static directory.
- Database backups are encrypted using a dedicated Fernet key.
- Tidak ada public file sharing; seluruh preview dan download melewati autentikasi aplikasi.
- Download and preview flow through the authenticated DMS.
- Database is not exposed outside Docker network.
- Login is locked for 15 minutes after five failed attempts.
- Secure cookies and CSRF protection are enabled behind Cloudflare HTTPS.
