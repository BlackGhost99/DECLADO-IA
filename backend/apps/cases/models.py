"""Dossiers douaniers : dossier, révisions, pièces rattachées, factures, lignes et décisions de code.

Toutes les tables portent `organization` (isolation, y compris pour les tables enfants).
Les services vérifient que chaque liaison reste dans la même société.
"""

from django.conf import settings
from django.db import models

from apps.core.models import OrganizationOwnedModel

AMOUNT = {"max_digits": 24, "decimal_places": 8, "null": True, "blank": True}


class CaseSequence(models.Model):
    """Compteur de références lisibles par société et par année (DOS-01)."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="+")
    year = models.PositiveSmallIntegerField()
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "year"], name="uniq_case_sequence")]

    def __str__(self):
        return f"{self.year}: {self.last_value}"


class CustomsCase(OrganizationOwnedModel):
    reference = models.CharField(max_length=40)
    title = models.CharField(max_length=200, blank=True)
    importer = models.ForeignKey(
        "clients.Importer", null=True, blank=True, on_delete=models.PROTECT, related_name="cases"
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    current_revision = models.OneToOneField(
        "CaseRevision", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "dossier"
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["organization", "reference"], name="uniq_case_reference")]

    def __str__(self):
        return self.reference

    @property
    def scope(self) -> str:
        return f"case:{self.id}"


class CaseRevision(OrganizationOwnedModel):
    class State(models.TextChoices):
        DRAFT = "draft", "Brouillon"
        IN_PREPARATION = "in_preparation", "En préparation"
        TO_VALIDATE = "to_validate", "À valider"
        TO_CORRECT = "to_correct", "À corriger"
        VALIDATED = "validated", "Validé en interne"
        ARCHIVED = "archived", "Archivé"

    class Mode(models.TextChoices):
        DEMO = "demo", "Démonstration (données fictives)"
        HISTORICAL = "historical", "Simulation sur référence historique"
        OPERATIONAL = "operational", "Opérationnel"

    class TransportMode(models.TextChoices):
        SEA = "sea", "Maritime"
        AIR = "air", "Aérien"
        ROAD = "road", "Routier"
        RAIL = "rail", "Ferroviaire"
        MULTIMODAL = "multimodal", "Multimodal"

    class Priority(models.TextChoices):
        NORMAL = "normal", "Normale"
        HIGH = "high", "Haute"
        URGENT = "urgent", "Urgente"

    EDITABLE_STATES = (State.DRAFT, State.IN_PREPARATION, State.TO_CORRECT)

    case = models.ForeignKey(CustomsCase, on_delete=models.PROTECT, related_name="revisions")
    revision_no = models.PositiveIntegerField()
    parent_revision = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    state = models.CharField(max_length=20, choices=State.choices, default=State.DRAFT)
    mode = models.CharField(max_length=20, choices=Mode.choices)
    territory = models.CharField(max_length=10, default="GA")
    planned_declaration_date = models.DateField(null=True, blank=True)
    regime = models.CharField(max_length=60, blank=True)
    # Renseignements de préparation saisis par l'utilisateur ; vides tant qu'ils sont inconnus.
    client_reference = models.CharField(max_length=60, blank=True)
    transport_mode = models.CharField(max_length=20, choices=TransportMode.choices, blank=True)
    entry_office = models.CharField(max_length=120, blank=True)
    origin_country = models.CharField(max_length=2, blank=True)  # ISO 3166 alpha-2, en texte
    provenance_country = models.CharField(max_length=2, blank=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    target_edition = models.ForeignKey(
        "tariffs.TariffEdition", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    reason = models.TextField(blank=True)
    # Champs remplis par la préparation automatique et pas encore confirmés par un agent.
    prefilled = models.JSONField(default=list, blank=True)
    # Taux de change saisis par un agent pour ce dossier : {"USD": {"rate": "605.5", "source": "…"}}.
    # Jamais déduits ni téléchargés ; l'euro et le franc CFA ont une parité fixe et n'y figurent pas.
    exchange_rates = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        verbose_name = "révision de dossier"
        ordering = ["case", "revision_no"]
        constraints = [models.UniqueConstraint(fields=["case", "revision_no"], name="uniq_case_revision")]

    def __str__(self):
        return f"{self.case.reference} r{self.revision_no}"

    @property
    def is_editable(self) -> bool:
        return self.state in self.EDITABLE_STATES


class CaseDocument(OrganizationOwnedModel):
    """Pièce rattachée à une révision ; l'accès aux octets dérive de la société du dossier."""

    class Usage(models.TextChoices):
        INVOICE = "invoice", "Facture"
        PACKING_LIST = "packing_list", "Liste de colisage"
        TRANSPORT = "transport", "Document de transport"
        INSURANCE = "insurance", "Assurance"
        FREIGHT = "freight", "Facture de fret"
        ORIGIN = "origin", "Certificat d'origine"
        OTHER = "other", "Autre pièce"

    revision = models.ForeignKey(CaseRevision, on_delete=models.PROTECT, related_name="documents")
    document = models.ForeignKey("documents.Document", on_delete=models.PROTECT, related_name="case_links")
    usage = models.CharField(max_length=20, choices=Usage.choices, default=Usage.OTHER)
    # Type proposé d'après le titre lu (code de la taxonomie) et ce qui le justifie ; jamais une
    # confirmation : celle-ci est une DocumentClassification signée par un agent (LEC-07).
    detected_type = models.CharField(max_length=60, blank=True)
    type_detection = models.JSONField(default=dict, blank=True)
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    # Remplacement : l'ancien rattachement reste visible et pointe vers son successeur.
    replaced_by = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="replaces")
    idempotency_key = models.CharField(max_length=100, blank=True)
    # Nouvelle révision (WF-04) : rattachement repris de la révision précédente, avec ses lectures.
    copied_from = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        verbose_name = "pièce du dossier"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_case_document_idempotency",
            )
        ]


class Invoice(OrganizationOwnedModel):
    revision = models.ForeignKey(CaseRevision, on_delete=models.PROTECT, related_name="invoices")
    ordinal = models.PositiveIntegerField()
    supplier_name = models.CharField(max_length=200, blank=True)
    # Acheteur ou destinataire tel qu'imprimé (« Bill to ») ; la fiche importateur du dossier reste la référence.
    buyer_name = models.CharField(max_length=200, blank=True)
    invoice_number = models.CharField(max_length=100, blank=True)
    invoice_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, blank=True)  # ISO 4217, tel que lu sur la facture
    incoterm = models.CharField(max_length=20, blank=True)
    declared_total = models.DecimalField(**AMOUNT)
    document = models.ForeignKey(CaseDocument, null=True, blank=True, on_delete=models.PROTECT, related_name="invoices")
    # Provenance de chaque valeur : « extracted », « inferred » (lue puis déduite) ou « manual » (saisie/corrigée).
    field_origins = models.JSONField(default=dict, blank=True)
    review_flags = models.JSONField(default=list, blank=True)
    # Nouvelle révision (WF-04) : facture reprise de la révision précédente, avec ses lectures.
    copied_from = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        verbose_name = "facture"
        ordering = ["revision", "ordinal"]
        constraints = [models.UniqueConstraint(fields=["revision", "ordinal"], name="uniq_invoice_ordinal")]


class EntryOrigin(models.TextChoices):
    MANUAL = "manual", "Saisi"
    EXTRACTED = "extracted", "Lu par extraction"
    INFERRED = "inferred", "Déduit"


class InvoiceLine(OrganizationOwnedModel):
    """Ligne facturée d'origine. La référence fournisseur n'est jamais un code douanier (EXT-04)."""

    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="lines")
    ordinal = models.PositiveIntegerField()
    source_reference = models.CharField(max_length=100, blank=True)
    description_raw = models.TextField(blank=True)
    quantity = models.DecimalField(**AMOUNT)
    unit = models.CharField(max_length=20, blank=True)
    unit_price = models.DecimalField(**AMOUNT)
    amount = models.DecimalField(**AMOUNT)
    origin_country = models.CharField(max_length=2, blank=True)
    entry_origin = models.CharField(max_length=20, choices=EntryOrigin.choices, default=EntryOrigin.MANUAL)
    # Preuve d'une saisie manuelle : pièce et page (index physique à partir de 1), ou note libre.
    evidence_document = models.ForeignKey(
        CaseDocument, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    evidence_page = models.PositiveIntegerField(null=True, blank=True)
    evidence_note = models.CharField(max_length=300, blank=True)
    # Rang de la ligne dans la lecture de la pièce : sert à rapprocher deux lectures (EXT-07).
    extraction_key = models.CharField(max_length=40, blank=True)
    field_origins = models.JSONField(default=dict, blank=True)
    review_flags = models.JSONField(default=list, blank=True)
    copied_from = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        verbose_name = "ligne facturée"
        ordering = ["invoice", "ordinal"]
        constraints = [models.UniqueConstraint(fields=["invoice", "ordinal"], name="uniq_invoice_line_ordinal")]


class CodeObservation(OrganizationOwnedModel):
    """Code tel que lu ou saisi, avec son champ source (COD-01). Jamais modifié : remplacé."""

    class Kind(models.TextChoices):
        CUSTOMS = "customs", "Code douanier"
        SUPPLIER = "supplier", "Référence fournisseur"
        AMBIGUOUS = "ambiguous", "Nature incertaine"

    invoice_line = models.ForeignKey(InvoiceLine, on_delete=models.PROTECT, related_name="code_observations")
    field_label = models.CharField(max_length=100)
    raw_code = models.CharField(max_length=60)
    normalized_code = models.CharField(max_length=40, null=True, blank=True)  # noqa: DJ001 - inconnu ≠ vide
    code_kind = models.CharField(max_length=20, choices=Kind.choices)
    claimed_scheme = models.CharField(max_length=60, blank=True)
    entry_origin = models.CharField(max_length=20, choices=EntryOrigin.choices, default=EntryOrigin.MANUAL)
    evidence_document = models.ForeignKey(
        CaseDocument, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    evidence_page = models.PositiveIntegerField(null=True, blank=True)
    source_span = models.ForeignKey(
        "extraction.SourceSpan", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    findings = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    superseded_at = models.DateTimeField(null=True, blank=True)
    superseded_by = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="supersedes"
    )

    class Meta:
        verbose_name = "code observé"
        ordering = ["created_at"]


class GoodsLine(OrganizationOwnedModel):
    """Marchandise à préparer, distincte de la ligne facturée (GRP-01 : liens conservés)."""

    revision = models.ForeignKey(CaseRevision, on_delete=models.PROTECT, related_name="goods_lines")
    ordinal = models.PositiveIntegerField()
    description = models.TextField(blank=True)
    attributes = models.JSONField(default=dict, blank=True)
    origin_country = models.CharField(max_length=2, blank=True)
    regime = models.CharField(max_length=60, blank=True)
    valuation_status = models.CharField(max_length=20, default="not_started")

    class Meta:
        verbose_name = "marchandise"
        ordering = ["revision", "ordinal"]
        constraints = [models.UniqueConstraint(fields=["revision", "ordinal"], name="uniq_goods_line_ordinal")]


class GoodsLineSource(OrganizationOwnedModel):
    goods_line = models.ForeignKey(GoodsLine, on_delete=models.PROTECT, related_name="sources")
    invoice_line = models.ForeignKey(InvoiceLine, on_delete=models.PROTECT, related_name="goods_sources")
    assigned_quantity = models.DecimalField(**AMOUNT)
    assigned_value = models.DecimalField(**AMOUNT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["goods_line", "invoice_line"], name="uniq_goods_line_source")]


class CodeCheck(OrganizationOwnedModel):
    """Résultat du contrôle d'un code présent contre une édition (COD-02). Historique conservé."""

    class State(models.TextChoices):
        MISSING = "missing", "Aucun code douanier"
        AMBIGUOUS = "ambiguous", "Nature ou valeur du code ambiguë"
        INCOMPLETE = "incomplete", "Code incomplet"
        NOT_FOUND = "not_found", "Code introuvable"
        EDITION_MISMATCH = "edition_mismatch", "Présent dans une autre édition seulement"
        INCONSISTENT = "inconsistent", "Incohérent avec la marchandise"
        RECOGNIZED = "recognized", "Retrouvé dans le référentiel"

    goods_line = models.ForeignKey(GoodsLine, on_delete=models.PROTECT, related_name="code_checks")
    observation = models.ForeignKey(
        CodeObservation, null=True, blank=True, on_delete=models.PROTECT, related_name="checks"
    )
    target_edition = models.ForeignKey("tariffs.TariffEdition", on_delete=models.PROTECT, related_name="+")
    node = models.ForeignKey("tariffs.TariffNode", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    state = models.CharField(max_length=20, choices=State.choices)
    findings = models.JSONField(default=list)
    checked_input_hash = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        verbose_name = "contrôle de code"
        ordering = ["-created_at"]


class ClassificationDecision(OrganizationOwnedModel):
    """Décision humaine attribuée (COD-03, COD-07). Ajout seul ; une nouvelle décision remplace l'ancienne."""

    class Action(models.TextChoices):
        CONFIRM = "confirm", "Confirmer le code présent"
        COMPLETE = "complete", "Compléter un code incomplet"
        REPLACE = "replace", "Remplacer le code présent"
        CLASSIFY = "classify", "Classer une marchandise sans code"

    goods_line = models.ForeignKey(GoodsLine, on_delete=models.PROTECT, related_name="decisions")
    original_observation = models.ForeignKey(
        CodeObservation, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    code_check = models.ForeignKey(CodeCheck, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    selected_node = models.ForeignKey("tariffs.TariffNode", on_delete=models.PROTECT, related_name="+")
    selected_code = models.CharField(max_length=20)  # instantané textuel, zéros conservés
    proposal = models.ForeignKey(
        "ClassificationProposal", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    edition = models.ForeignKey("tariffs.TariffEdition", on_delete=models.PROTECT, related_name="+")
    action = models.CharField(max_length=20, choices=Action.choices)
    reason = models.TextField()
    evidence_refs = models.JSONField(default=list, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    goods_line_version = models.PositiveIntegerField()
    input_hash = models.CharField(max_length=64)

    class Meta:
        verbose_name = "décision de classement"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Une décision de classement n'est jamais modifiée : en enregistrer une nouvelle.")
        super().save(*args, **kwargs)


class ProposalSet(OrganizationOwnedModel):
    """Aide au classement (COD-04 à COD-06) : produite seulement si nécessaire ou demandée.

    Chaque proposition référence une ligne existante de l'édition ; sans preuve suffisante,
    l'ensemble ne contient que des questions. Aucun code n'est choisi automatiquement.
    """

    goods_line = models.ForeignKey(GoodsLine, on_delete=models.PROTECT, related_name="proposal_sets")
    code_check = models.ForeignKey(CodeCheck, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    edition = models.ForeignKey("tariffs.TariffEdition", on_delete=models.PROTECT, related_name="+")
    trigger = models.CharField(max_length=30)  # état du contrôle ou « explicit »
    query = models.TextField(blank=True)
    producer = models.CharField(max_length=60)  # « recherche-referentiel 1.0 » ; un modèle d'IA serait nommé ici
    questions = models.JSONField(default=list, blank=True)
    input_hash = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        verbose_name = "aide au classement"
        ordering = ["-created_at"]


class ClassificationProposal(OrganizationOwnedModel):
    proposal_set = models.ForeignKey(ProposalSet, on_delete=models.PROTECT, related_name="proposals")
    node = models.ForeignKey("tariffs.TariffNode", on_delete=models.PROTECT, related_name="+")
    code = models.CharField(max_length=20)
    rank = models.PositiveSmallIntegerField()
    reasons = models.JSONField(default=list)
    note_refs = models.JSONField(default=list, blank=True)
    distinguishing = models.JSONField(default=list, blank=True)
    retrieval_score = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["proposal_set", "rank"]


class AIClassification(OrganizationOwnedModel):
    """Choix de l'IA parmi les propositions d'un ensemble (CLA-IA) : journal append-only.

    L'IA ne reçoit que la désignation et les lignes candidates du tarif ; elle ne peut choisir
    qu'une proposition existante, avec un passage de la désignation qui la justifie. Le choix
    reste une proposition : seul un agent décide le code.
    """

    class Status(models.TextChoices):
        SENT = "sent", "Envoyée"
        CLIENT_REFUSED = "client_refused", "Non envoyée : le client refuse"
        CAP_REACHED = "cap_reached", "Non envoyée : plafond du mois atteint"
        FAILED = "failed", "Échec du fournisseur"

    proposal_set = models.ForeignKey(ProposalSet, on_delete=models.PROTECT, related_name="ai_choices")
    goods_line = models.ForeignKey(GoodsLine, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=20, choices=Status.choices)
    trigger = models.CharField(max_length=20)  # auto, on_demand
    provider = models.CharField(max_length=40, blank=True)
    model = models.CharField(max_length=80, blank=True)
    free_tier = models.BooleanField(default=False)
    chosen = models.ForeignKey(
        ClassificationProposal, null=True, blank=True, on_delete=models.PROTECT, related_name="ai_choices"
    )
    reason = models.TextField(blank=True)
    evidence = models.CharField(max_length=200, blank=True)
    rejected = models.JSONField(default=list, blank=True)  # [{"reason"}] réponses écartées par le contrôle
    sent_chars = models.PositiveIntegerField(default=0)
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    cost_estimate = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)  # $, inconnu ≠ 0
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=40, blank=True)
    error_message = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        verbose_name = "choix de code par l'IA"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "created_at"])]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Le journal de l'IA n'est jamais modifié.")
        super().save(*args, **kwargs)


class RevisionDecision(OrganizationOwnedModel):
    """WF-01 à WF-03 : soumission, retour pour correction et validation interne d'une révision.

    Ajout seul. L'empreinte couvre le calcul et les données soumises : une validation sur un calcul
    qui a changé depuis la soumission est refusée. « Validé » reste une validation interne.
    """

    class Kind(models.TextChoices):
        SUBMITTED = "submitted", "Soumis pour validation"
        RETURNED = "returned", "Retourné pour correction"
        VALIDATED = "validated", "Validé en interne"

    revision = models.ForeignKey(CaseRevision, on_delete=models.PROTECT, related_name="decisions")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    reason = models.TextField(blank=True)
    fingerprint = models.CharField(max_length=64)
    # Calcul et contrôles au moment de la décision : le calcul validé est figé ici.
    snapshot = models.JSONField(default=dict)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.revision} · {self.get_kind_display()}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Une décision de validation n'est jamais réécrite : en enregistrer une nouvelle.")
        super().save(*args, **kwargs)


class CaseExport(OrganizationOwnedModel):
    """EXP-01 à EXP-03 : fichier exporté d'une révision, conservé tel que généré (ajout seul).

    Le marquage est fixé à la génération : « brouillon » tant que la révision n'est pas validée,
    « validé en interne » ensuite. Jamais une acceptation par la Douane.
    """

    class Format(models.TextChoices):
        PDF = "pdf", "Récapitulatif PDF"
        XLSX = "xlsx", "Détail Excel"
        DAU = "dau", "Projet de déclaration (modèle DAU)"

    class Marking(models.TextChoices):
        DRAFT = "draft", "Brouillon"
        VALIDATED = "validated", "Validé en interne"

    revision = models.ForeignKey(CaseRevision, on_delete=models.PROTECT, related_name="exports")
    format = models.CharField(max_length=10, choices=Format.choices)
    marking = models.CharField(max_length=20, choices=Marking.choices)
    filename = models.CharField(max_length=120)
    object_key = models.CharField(max_length=200, unique=True, editable=False)
    sha256 = models.CharField(max_length=64)
    bytes = models.PositiveBigIntegerField()
    # Empreinte du calcul exporté : celle de la décision de validation quand le dossier est validé.
    calculation_fingerprint = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.filename

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Un export n'est jamais réécrit : en générer un nouveau.")
        super().save(*args, **kwargs)
