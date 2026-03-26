"""
vocabulary.py
=============
ISO QHSE Vocabulary for RAG / NLP scanning — QALITAS Project

Two flat dictionaries:
    ISO_VOCABULARY_EN  —  English surface forms
    ISO_VOCABULARY_FR  —  French surface forms

Format
------
Each entry is:

    "canonical term": {
        "standards": ["ISO9001", "ISO14001", ...],   # which standards own this term
        "forms":     ["surface form 1", "form 2", ...],  # all forms to scan for
    }

Standards tags used
-------------------
    "ISO9001"   — ISO 9001:2015  Quality Management Systems
    "ISO14001"  — ISO 14001:2015 Environmental Management Systems
    "ISO45001"  — ISO 45001:2018 Occupational Health & Safety (HLS cross-reference)
    "ISO22000"  — ISO 22000:2018 Food Safety Management (HLS cross-reference)

HLS terms (High-Level Structure / Annex SL) appear in all four standards.
Standard-specific terms are tagged with only the owning standard(s).

Usage
-----
    from vocabulary import ISO_VOCABULARY_EN, ISO_VOCABULARY_FR

    # Filter to terms relevant to a specific standard
    iso9001_terms = {
        key: entry
        for key, entry in ISO_VOCABULARY_EN.items()
        if "ISO9001" in entry["standards"]
    }

    # Build a flat surface-form → canonical-key lookup, scoped to a standard
    def build_lookup(vocab, norm_filter: list[str]) -> dict[str, str]:
        lookup = {}
        for key, entry in vocab.items():
            if any(s in entry["standards"] for s in norm_filter):
                for form in entry["forms"]:
                    lookup[form.lower()] = key
        return lookup

    en_lookup = build_lookup(ISO_VOCABULARY_EN, ["ISO9001"])
    fr_lookup = build_lookup(ISO_VOCABULARY_FR, ["ISO14001"])
"""



# =============================================================================
# ENGLISH vocabulary
# =============================================================================

ISO_VOCABULARY_EN: dict[str, dict] = {

    # -------------------------------------------------------------------------
    # Leadership & Governance  (HLS §5)
    # -------------------------------------------------------------------------

    "top management": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "top management",
            "senior management",
            "leadership",
            "upper management",
            "executive management",
            "executive team",
            "governing body",
        ],
    },

    "management review": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "management review",
            "management review meeting",
            "system review",
            "review by management",
            "periodic management review",
            "annual management review",
        ],
    },

    "leadership and commitment": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "leadership and commitment",
            "management commitment",
            "top management commitment",
            "demonstration of leadership",
            "commitment of management",
        ],
    },

    "organizational roles and responsibilities": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "organizational roles and responsibilities",
            "roles and responsibilities",
            "roles responsibilities and authorities",
            "responsibility assignment",
            "authority assignment",
            "accountability",
        ],
    },

    "interested parties": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "interested parties",
            "stakeholders",
            "relevant parties",
            "concerned parties",
            "external parties",
            "internal parties",
        ],
    },

    "quality policy": {
        "standards": ["ISO9001"],
        "forms": [
            "quality policy",
            "quality statement",
            "quality commitment",
            "quality declaration",
            "policy for quality",
        ],
    },

    "environmental policy": {
        "standards": ["ISO14001"],
        "forms": [
            "environmental policy",
            "environmental commitment",
            "environmental statement",
            "environmental declaration",
            "policy for environment",
        ],
    },

    "occupational health and safety policy": {
        "standards": ["ISO45001"],
        "forms": [
            "occupational health and safety policy",
            "OH&S policy",
            "OHS policy",
            "health and safety policy",
            "safety policy",
        ],
    },

    "customer focus": {
        "standards": ["ISO9001"],
        "forms": [
            "customer focus",
            "customer orientation",
            "customer requirements",
            "customer needs",
            "customer expectations",
            "focus on customer",
        ],
    },

    # -------------------------------------------------------------------------
    # Context  (HLS §4)
    # -------------------------------------------------------------------------

    "context of the organization": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "context of the organization",
            "organizational context",
            "internal and external issues",
            "internal issues",
            "external issues",
            "understanding the organization",
            "understanding the context",
        ],
    },

    "scope": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "scope",
            "scope of the management system",
            "scope of the QMS",
            "scope of the EMS",
            "system boundaries",
            "applicability",
        ],
    },

    "quality management system": {
        "standards": ["ISO9001"],
        "forms": [
            "quality management system",
            "QMS",
            "quality system",
            "management system for quality",
        ],
    },

    "environmental management system": {
        "standards": ["ISO14001"],
        "forms": [
            "environmental management system",
            "EMS",
            "environmental system",
            "management system for environment",
        ],
    },

    "occupational health and safety management system": {
        "standards": ["ISO45001"],
        "forms": [
            "occupational health and safety management system",
            "OH&S management system",
            "OHS management system",
            "safety management system",
        ],
    },

    # -------------------------------------------------------------------------
    # Planning  (HLS §6)
    # -------------------------------------------------------------------------

    "risks and opportunities": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "risks and opportunities",
            "risk and opportunity",
            "threats and opportunities",
            "risks opportunities",
            "actions to address risks",
        ],
    },

    "risk": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "risk",
            "risks",
            "risk assessment",
            "risk analysis",
            "risk evaluation",
            "risk identification",
            "risk management",
        ],
    },

    "risk-based thinking": {
        "standards": ["ISO9001", "ISO14001"],
        "forms": [
            "risk-based thinking",
            "risk based thinking",
            "risk-based approach",
            "preventive approach",
            "preventive thinking",
        ],
    },

    "objectives": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "objectives",
            "quality objectives",
            "environmental objectives",
            "targets",
            "goals",
            "key results",
            "intended results",
        ],
    },

    "planning of changes": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "planning of changes",
            "change management",
            "change planning",
            "change control",
            "management of change",
            "planned changes",
            "unintended changes",
        ],
    },

    "actions to address risks and opportunities": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "actions to address risks and opportunities",
            "risk treatment",
            "risk mitigation",
            "preventive actions",
            "opportunity actions",
        ],
    },

    "compliance obligations": {
        "standards": ["ISO9001", "ISO14001", "ISO45001"],
        "forms": [
            "compliance obligations",
            "legal requirements",
            "regulatory requirements",
            "legal and other requirements",
            "statutory requirements",
            "applicable requirements",
            "binding obligations",
        ],
    },

    "environmental aspects": {
        "standards": ["ISO14001"],
        "forms": [
            "environmental aspects",
            "significant environmental aspects",
            "environmental elements",
            "environmental interactions",
        ],
    },

    "environmental impact": {
        "standards": ["ISO14001"],
        "forms": [
            "environmental impact",
            "environmental impacts",
            "environmental effect",
            "environmental consequence",
            "impact on the environment",
        ],
    },

    "life cycle perspective": {
        "standards": ["ISO14001"],
        "forms": [
            "life cycle perspective",
            "life cycle",
            "lifecycle",
            "life cycle thinking",
            "life cycle assessment",
            "LCA",
            "cradle to grave",
            "end of life",
        ],
    },

    "pollution prevention": {
        "standards": ["ISO14001"],
        "forms": [
            "pollution prevention",
            "prevent pollution",
            "emission control",
            "waste reduction",
            "emission reduction",
            "reduction at source",
        ],
    },

    "hazard identification": {
        "standards": ["ISO45001"],
        "forms": [
            "hazard identification",
            "hazard",
            "hazards",
            "identify hazards",
            "hazard assessment",
            "danger identification",
        ],
    },

    "emergency preparedness": {
        "standards": ["ISO9001", "ISO14001", "ISO45001"],
        "forms": [
            "emergency preparedness",
            "emergency preparedness and response",
            "emergency response",
            "emergency plan",
            "contingency plan",
            "crisis management",
            "incident response",
        ],
    },

    # -------------------------------------------------------------------------
    # Support  (HLS §7)
    # -------------------------------------------------------------------------

    "documented information": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "documented information",
            "documents",
            "records",
            "documentation",
            "documented procedures",
            "quality manual",
            "documented evidence",
        ],
    },

    "maintain documented information": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "maintain documented information",
            "maintain documentation",
            "keep up to date",
            "document maintenance",
        ],
    },

    "retain documented information": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "retain documented information",
            "retain records",
            "evidence retention",
            "archiving",
            "record retention",
            "objective evidence",
        ],
    },

    "control of documented information": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "control of documented information",
            "document control",
            "documentation control",
            "version control",
            "document management",
        ],
    },

    "competence": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "competence",
            "competences",
            "competencies",
            "qualification",
            "skills",
            "knowledge and skills",
            "ability",
            "expertise",
        ],
    },

    "awareness": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "awareness",
            "awareness training",
            "personnel awareness",
            "staff awareness",
            "raising awareness",
        ],
    },

    "communication": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "communication",
            "internal communication",
            "external communication",
            "communicating",
            "information sharing",
            "reporting",
        ],
    },

    "resources": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "resources",
            "human resources",
            "financial resources",
            "provision of resources",
            "resource management",
        ],
    },

    "infrastructure": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "infrastructure",
            "facilities",
            "equipment",
            "buildings",
            "hardware",
            "software",
            "utilities",
        ],
    },

    "organizational knowledge": {
        "standards": ["ISO9001"],
        "forms": [
            "organizational knowledge",
            "organisation knowledge",
            "knowledge management",
            "lessons learned",
            "knowledge base",
            "institutional knowledge",
        ],
    },

    "training": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "training",
            "education",
            "professional development",
            "staff training",
            "employee training",
        ],
    },

    # -------------------------------------------------------------------------
    # Operation  (HLS §8)
    # -------------------------------------------------------------------------

    "operational planning and control": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "operational planning and control",
            "operational control",
            "process control",
            "operational planning",
            "operations management",
            "control of operations",
        ],
    },

    "process approach": {
        "standards": ["ISO9001", "ISO14001"],
        "forms": [
            "process approach",
            "process management",
            "process mapping",
            "process interactions",
            "manage processes",
        ],
    },

    "PDCA": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "PDCA",
            "plan do check act",
            "plan-do-check-act",
            "Deming cycle",
            "PDSA",
            "plan check act",
        ],
    },

    "design and development": {
        "standards": ["ISO9001"],
        "forms": [
            "design and development",
            "design",
            "development",
            "design process",
            "product design",
            "service design",
            "design inputs",
            "design outputs",
            "design review",
            "design validation",
            "design verification",
        ],
    },

    "requirements for products and services": {
        "standards": ["ISO9001"],
        "forms": [
            "requirements for products and services",
            "product requirements",
            "service requirements",
            "product and service requirements",
        ],
    },

    "production and service provision": {
        "standards": ["ISO9001"],
        "forms": [
            "production and service provision",
            "service provision",
            "production",
            "manufacturing",
            "service delivery",
            "controlled conditions",
        ],
    },

    "control of external providers": {
        "standards": ["ISO9001", "ISO14001", "ISO45001"],
        "forms": [
            "control of external providers",
            "external providers",
            "supplier control",
            "vendor management",
            "supplier evaluation",
            "purchasing control",
            "control of outsourcing",
        ],
    },

    "outsourcing": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "outsourcing",
            "outsourced processes",
            "external provision",
            "subcontracting",
            "third-party processes",
        ],
    },

    "identification and traceability": {
        "standards": ["ISO9001"],
        "forms": [
            "identification and traceability",
            "traceability",
            "product identification",
            "batch number",
            "lot number",
            "tracking",
        ],
    },

    "nonconforming outputs": {
        "standards": ["ISO9001"],
        "forms": [
            "nonconforming outputs",
            "control of nonconforming outputs",
            "nonconforming products",
            "nonconforming services",
            "defective outputs",
        ],
    },

    "release of products and services": {
        "standards": ["ISO9001"],
        "forms": [
            "release of products and services",
            "product release",
            "service release",
            "acceptance criteria",
            "release criteria",
        ],
    },

    # -------------------------------------------------------------------------
    # Performance Evaluation  (HLS §9)
    # -------------------------------------------------------------------------

    "monitoring and measurement": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "monitoring and measurement",
            "monitoring",
            "measurement",
            "performance measurement",
            "measuring",
        ],
    },

    "analysis and evaluation": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "analysis and evaluation",
            "data analysis",
            "evaluation",
            "results analysis",
            "trend analysis",
            "statistical analysis",
        ],
    },

    "customer satisfaction": {
        "standards": ["ISO9001"],
        "forms": [
            "customer satisfaction",
            "customer feedback",
            "customer perception",
            "customer complaints",
            "satisfaction survey",
            "NPS",
            "CSAT",
        ],
    },

    "internal audit": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "internal audit",
            "internal audits",
            "audit programme",
            "audit program",
            "audit schedule",
            "first-party audit",
            "audit findings",
            "audit criteria",
        ],
    },

    "performance evaluation": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "performance evaluation",
            "system effectiveness",
            "evaluate performance",
            "performance assessment",
            "evaluate effectiveness",
        ],
    },

    "environmental performance": {
        "standards": ["ISO14001"],
        "forms": [
            "environmental performance",
            "environmental results",
            "environmental KPIs",
            "environmental indicators",
            "environmental performance indicators",
        ],
    },

    "compliance evaluation": {
        "standards": ["ISO9001", "ISO14001", "ISO45001"],
        "forms": [
            "compliance evaluation",
            "evaluate compliance",
            "compliance check",
            "conformity assessment",
            "compliance verification",
            "compliance status",
        ],
    },

    "indicator": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "indicator",
            "indicators",
            "KPI",
            "KPIs",
            "key performance indicator",
            "performance indicator",
            "measurement indicator",
        ],
    },

    # -------------------------------------------------------------------------
    # Improvement  (HLS §10)
    # -------------------------------------------------------------------------

    "continual improvement": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "continual improvement",
            "continuous improvement",
            "ongoing improvement",
            "improvement process",
            "kaizen",
            "improvement cycle",
        ],
    },

    "corrective action": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "corrective action",
            "corrective actions",
            "CAPA",
            "CAR",
            "root cause analysis",
            "root cause correction",
            "corrective measure",
        ],
    },

    "nonconformity": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "nonconformity",
            "nonconformities",
            "non-conformity",
            "non-conformance",
            "deviation",
            "NC",
            "noncompliance",
            "defect",
            "deficiency",
        ],
    },

    "conformity": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "conformity",
            "conformance",
            "compliance",
            "fulfilment of requirements",
            "meeting requirements",
        ],
    },

    "improvement": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "improvement",
            "improvements",
            "improve",
            "performance improvement",
            "system improvement",
            "breakthrough",
            "innovation",
        ],
    },

    "requirement": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "requirement",
            "requirements",
            "specified requirement",
            "implied requirement",
            "obligatory requirement",
            "criterion",
        ],
    },
}


# =============================================================================
# FRENCH vocabulary
# =============================================================================

ISO_VOCABULARY_FR: dict[str, dict] = {

    # -------------------------------------------------------------------------
    # Leadership & Gouvernance  (HLS §5)
    # -------------------------------------------------------------------------

    "direction": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "direction",
            "haute direction",
            "dirigeants",
            "encadrement supérieur",
            "équipe de direction",
            "responsables",
        ],
    },

    "revue de direction": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "revue de direction",
            "revue de management",
            "revue du système de management",
            "bilan de direction",
            "revue annuelle",
            "revue périodique",
        ],
    },

    "leadership et engagement": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "leadership et engagement",
            "engagement de la direction",
            "implication de la direction",
            "démonstration du leadership",
            "engagement managérial",
        ],
    },

    "rôles responsabilités et autorités": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "rôles responsabilités et autorités",
            "rôles et responsabilités",
            "responsabilités et autorités",
            "attribution des responsabilités",
            "délégation d'autorité",
        ],
    },

    "parties intéressées": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "parties intéressées",
            "parties prenantes",
            "parties concernées",
            "parties pertinentes",
            "tiers concernés",
        ],
    },

    "politique qualité": {
        "standards": ["ISO9001"],
        "forms": [
            "politique qualité",
            "politique de qualité",
            "déclaration qualité",
            "engagement qualité",
            "orientations qualité",
        ],
    },

    "politique environnementale": {
        "standards": ["ISO14001"],
        "forms": [
            "politique environnementale",
            "politique en matière d'environnement",
            "engagement environnemental",
            "déclaration environnementale",
            "orientations environnementales",
        ],
    },

    "politique santé sécurité au travail": {
        "standards": ["ISO45001"],
        "forms": [
            "politique santé sécurité au travail",
            "politique SST",
            "politique de sécurité",
            "politique santé et sécurité",
        ],
    },

    "orientation client": {
        "standards": ["ISO9001"],
        "forms": [
            "orientation client",
            "focus client",
            "besoins des clients",
            "attentes des clients",
            "exigences des clients",
            "satisfaction client",
        ],
    },

    # -------------------------------------------------------------------------
    # Contexte  (HLS §4)
    # -------------------------------------------------------------------------

    "contexte de l'organisme": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "contexte de l'organisme",
            "contexte organisationnel",
            "enjeux internes et externes",
            "enjeux internes",
            "enjeux externes",
            "compréhension de l'organisme",
        ],
    },

    "domaine d'application": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "domaine d'application",
            "périmètre",
            "champ d'application",
            "limites du système",
            "applicabilité",
        ],
    },

    "système de management de la qualité": {
        "standards": ["ISO9001"],
        "forms": [
            "système de management de la qualité",
            "SMQ",
            "système qualité",
            "système de management qualité",
        ],
    },

    "système de management environnemental": {
        "standards": ["ISO14001"],
        "forms": [
            "système de management environnemental",
            "SME",
            "système environnemental",
            "système de management de l'environnement",
        ],
    },

    "système de management de la santé et sécurité au travail": {
        "standards": ["ISO45001"],
        "forms": [
            "système de management de la santé et sécurité au travail",
            "système de management SST",
            "SMSST",
            "système SST",
        ],
    },

    # -------------------------------------------------------------------------
    # Planification  (HLS §6)
    # -------------------------------------------------------------------------

    "risques et opportunités": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "risques et opportunités",
            "risques et opportunites",
            "menaces et opportunités",
            "opportunités et risques",
            "actions face aux risques",
        ],
    },

    "risque": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "risque",
            "risques",
            "analyse des risques",
            "évaluation des risques",
            "identification des risques",
            "gestion des risques",
            "management des risques",
        ],
    },

    "approche par les risques": {
        "standards": ["ISO9001", "ISO14001"],
        "forms": [
            "approche par les risques",
            "réflexion fondée sur le risque",
            "pensée basée sur les risques",
            "approche préventive",
            "approche risque",
        ],
    },

    "objectifs": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "objectifs",
            "objectifs qualité",
            "objectifs environnementaux",
            "cibles",
            "buts",
            "résultats attendus",
            "résultats escomptés",
        ],
    },

    "planification des modifications": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "planification des modifications",
            "gestion des changements",
            "maîtrise des modifications",
            "management du changement",
            "modifications planifiées",
            "changements planifiés",
        ],
    },

    "actions face aux risques et opportunités": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "actions face aux risques et opportunités",
            "actions à mettre en œuvre face aux risques",
            "traitement des risques",
            "atténuation des risques",
            "actions préventives",
        ],
    },

    "obligations de conformité": {
        "standards": ["ISO9001", "ISO14001", "ISO45001"],
        "forms": [
            "obligations de conformité",
            "exigences légales",
            "exigences réglementaires",
            "exigences légales et autres exigences",
            "exigences applicables",
            "obligations réglementaires",
            "conformité réglementaire",
        ],
    },

    "aspects environnementaux": {
        "standards": ["ISO14001"],
        "forms": [
            "aspects environnementaux",
            "aspects environnementaux significatifs",
            "AES",
            "aspects significatifs",
            "éléments environnementaux",
        ],
    },

    "impact environnemental": {
        "standards": ["ISO14001"],
        "forms": [
            "impact environnemental",
            "impacts environnementaux",
            "effets sur l'environnement",
            "conséquences environnementales",
            "incidence environnementale",
        ],
    },

    "perspective de cycle de vie": {
        "standards": ["ISO14001"],
        "forms": [
            "perspective de cycle de vie",
            "cycle de vie",
            "analyse du cycle de vie",
            "ACV",
            "approche cycle de vie",
            "du berceau à la tombe",
        ],
    },

    "prévention de la pollution": {
        "standards": ["ISO14001"],
        "forms": [
            "prévention de la pollution",
            "prévenir la pollution",
            "réduction des émissions",
            "lutte contre la pollution",
            "réduction à la source",
            "contrôle des émissions",
        ],
    },

    "identification des dangers": {
        "standards": ["ISO45001"],
        "forms": [
            "identification des dangers",
            "danger",
            "dangers",
            "identifier les dangers",
            "évaluation des dangers",
        ],
    },

    "préparation aux situations d'urgence": {
        "standards": ["ISO9001", "ISO14001", "ISO45001"],
        "forms": [
            "préparation aux situations d'urgence",
            "situations d'urgence",
            "préparation et réponse aux situations d'urgence",
            "réponse aux urgences",
            "plan d'urgence",
            "plan d'intervention",
            "gestion des crises",
        ],
    },

    # -------------------------------------------------------------------------
    # Support  (HLS §7)
    # -------------------------------------------------------------------------

    "informations documentées": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "informations documentées",
            "information documentée",
            "documents",
            "enregistrements",
            "documentation",
            "procédures documentées",
            "manuel qualité",
            "preuves documentées",
        ],
    },

    "tenir à jour les informations documentées": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "tenir à jour les informations documentées",
            "tenir à jour",
            "maintenir à jour",
            "mise à jour de la documentation",
            "maintenir la documentation",
        ],
    },

    "conserver les informations documentées": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "conserver les informations documentées",
            "conserver les enregistrements",
            "conservation des preuves",
            "archivage",
            "conservation des enregistrements",
            "preuves objectives",
        ],
    },

    "maîtrise des informations documentées": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "maîtrise des informations documentées",
            "maîtrise documentaire",
            "contrôle des documents",
            "gestion documentaire",
            "contrôle des versions",
            "management documentaire",
        ],
    },

    "compétence": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "compétence",
            "compétences",
            "qualification",
            "aptitude",
            "savoir-faire",
            "habilitation",
            "expertise",
        ],
    },

    "sensibilisation": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "sensibilisation",
            "prise de conscience",
            "formation sensibilisation",
            "sensibiliser le personnel",
            "conscience professionnelle",
        ],
    },

    "communication": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "communication",
            "communication interne",
            "communication externe",
            "diffusion de l'information",
            "partage d'information",
            "reporting",
        ],
    },

    "ressources": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "ressources",
            "ressources humaines",
            "ressources financières",
            "provision de ressources",
            "gestion des ressources",
            "moyens",
        ],
    },

    "infrastructure": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "infrastructure",
            "installations",
            "équipements",
            "bâtiments",
            "matériels",
            "logiciels",
            "moyens matériels",
        ],
    },

    "connaissances organisationnelles": {
        "standards": ["ISO9001"],
        "forms": [
            "connaissances organisationnelles",
            "gestion des connaissances",
            "retour d'expérience",
            "REX",
            "capitalisation des connaissances",
            "base de connaissances",
        ],
    },

    "formation": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "formation",
            "formation professionnelle",
            "développement des compétences",
            "formation du personnel",
            "plan de formation",
        ],
    },

    # -------------------------------------------------------------------------
    # Réalisation  (HLS §8)
    # -------------------------------------------------------------------------

    "planification et maîtrise opérationnelles": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "planification et maîtrise opérationnelles",
            "maîtrise opérationnelle",
            "contrôle opérationnel",
            "planification opérationnelle",
            "maîtrise des activités",
        ],
    },

    "approche processus": {
        "standards": ["ISO9001", "ISO14001"],
        "forms": [
            "approche processus",
            "gestion par processus",
            "management des processus",
            "cartographie des processus",
            "interactions entre processus",
        ],
    },

    "PDCA": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "PDCA",
            "Planifier Réaliser Vérifier Agir",
            "roue de Deming",
            "cycle PDCA",
            "amélioration itérative",
        ],
    },

    "conception et développement": {
        "standards": ["ISO9001"],
        "forms": [
            "conception et développement",
            "conception",
            "développement",
            "bureau d'études",
            "éléments d'entrée de la conception",
            "éléments de sortie de la conception",
            "revue de conception",
            "validation de la conception",
            "vérification de la conception",
        ],
    },

    "exigences relatives aux produits et services": {
        "standards": ["ISO9001"],
        "forms": [
            "exigences relatives aux produits et services",
            "exigences produits",
            "exigences services",
            "exigences applicables aux produits",
        ],
    },

    "réalisation des activités opérationnelles": {
        "standards": ["ISO9001"],
        "forms": [
            "réalisation des activités opérationnelles",
            "réalisation des activités",
            "prestation de services",
            "production",
            "fabrication",
            "exécution des activités",
        ],
    },

    "maîtrise des fournisseurs externes": {
        "standards": ["ISO9001", "ISO14001", "ISO45001"],
        "forms": [
            "maîtrise des fournisseurs externes",
            "fournisseurs externes",
            "maîtrise des prestataires",
            "évaluation des fournisseurs",
            "sélection des fournisseurs",
            "achats",
            "contrôle des sous-traitants",
        ],
    },

    "externalisation": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "externalisation",
            "processus externalisés",
            "sous-traitance",
            "prestataires",
            "tiers",
            "activités externalisées",
        ],
    },

    "identification et traçabilité": {
        "standards": ["ISO9001"],
        "forms": [
            "identification et traçabilité",
            "traçabilité",
            "identification du produit",
            "numéro de lot",
            "numéro de série",
            "suivi",
        ],
    },

    "éléments de sortie non conformes": {
        "standards": ["ISO9001"],
        "forms": [
            "éléments de sortie non conformes",
            "produits non conformes",
            "services non conformes",
            "sorties non conformes",
            "maîtrise des non-conformités",
        ],
    },

    "libération des produits et services": {
        "standards": ["ISO9001"],
        "forms": [
            "libération des produits et services",
            "libération du produit",
            "critères d'acceptation",
            "autorisation de livraison",
        ],
    },

    # -------------------------------------------------------------------------
    # Évaluation des performances  (HLS §9)
    # -------------------------------------------------------------------------

    "surveillance et mesure": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "surveillance et mesure",
            "surveillance",
            "mesure",
            "suivi",
            "mesure des performances",
            "surveillance des performances",
        ],
    },

    "analyse et évaluation": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "analyse et évaluation",
            "analyse des données",
            "évaluation",
            "analyse des résultats",
            "analyse de tendances",
            "analyse statistique",
        ],
    },

    "satisfaction du client": {
        "standards": ["ISO9001"],
        "forms": [
            "satisfaction du client",
            "satisfaction client",
            "perception du client",
            "réclamations clients",
            "retour client",
            "enquête de satisfaction",
        ],
    },

    "audit interne": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "audit interne",
            "audits internes",
            "programme d'audit",
            "programme d'audit interne",
            "calendrier d'audit",
            "audit de première partie",
            "résultats d'audit",
            "critères d'audit",
        ],
    },

    "évaluation des performances": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "évaluation des performances",
            "évaluation de l'efficacité du système",
            "mesure des résultats",
            "évaluation du système",
        ],
    },

    "performance environnementale": {
        "standards": ["ISO14001"],
        "forms": [
            "performance environnementale",
            "résultats environnementaux",
            "indicateurs environnementaux",
            "indicateurs de performance environnementale",
        ],
    },

    "évaluation de la conformité": {
        "standards": ["ISO9001", "ISO14001", "ISO45001"],
        "forms": [
            "évaluation de la conformité",
            "vérification de la conformité",
            "bilan de conformité",
            "état de conformité",
            "contrôle de conformité",
            "conformité aux obligations",
        ],
    },

    "indicateur": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "indicateur",
            "indicateurs",
            "indicateur de performance",
            "indicateurs clés",
            "KPI",
            "tableau de bord",
            "mesure",
        ],
    },

    # -------------------------------------------------------------------------
    # Amélioration  (HLS §10)
    # -------------------------------------------------------------------------

    "amélioration continue": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "amélioration continue",
            "amélioration permanente",
            "progrès continu",
            "démarche d'amélioration",
            "kaizen",
            "amélioration itérative",
        ],
    },

    "action corrective": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "action corrective",
            "actions correctives",
            "CAPA",
            "analyse des causes",
            "analyse des causes racines",
            "correction",
            "mesure corrective",
            "plan d'action correctif",
        ],
    },

    "non-conformité": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "non-conformité",
            "non-conformités",
            "NC",
            "écart",
            "défaut de conformité",
            "anomalie",
            "défaillance",
            "non-respect des exigences",
        ],
    },

    "conformité": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "conformité",
            "respect des exigences",
            "satisfaction des exigences",
            "être conforme",
        ],
    },

    "amélioration": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "amélioration",
            "améliorations",
            "améliorer",
            "amélioration des performances",
            "progrès",
            "optimisation",
            "gains",
        ],
    },

    "exigence": {
        "standards": ["ISO9001", "ISO14001", "ISO45001", "ISO22000"],
        "forms": [
            "exigence",
            "exigences",
            "besoin",
            "attente",
            "obligation",
            "critère",
            "prescription",
        ],
    },
}


# =============================================================================
# Helper — build a scoped surface-form → canonical-key lookup
# =============================================================================

def build_lookup(
    vocab: dict[str, dict],
    norm_filter: list[str],
) -> dict[str, str]:
    """
    Build a flat {surface_form_lower: canonical_key} lookup
    restricted to terms belonging to the given standards.

    Parameters
    ----------
    vocab : dict
        One of ISO_VOCABULARY_EN or ISO_VOCABULARY_FR.
    norm_filter : list[str]
        Standards to include, e.g. ["ISO9001"] or ["ISO9001", "ISO14001"].

    Returns
    -------
    dict[str, str]
        Maps every matching surface form (lowercased) to its canonical key.

    Example
    -------
    >>> lookup = build_lookup(ISO_VOCABULARY_EN, ["ISO9001"])
    >>> lookup.get("quality policy")
    'quality policy'
    >>> lookup.get("système de management environnemental")  # None — not ISO9001
    """
    lookup: dict[str, str] = {}
    for key, entry in vocab.items():
        if any(s in entry["standards"] for s in norm_filter):
            for form in entry["forms"]:
                lookup[form.lower()] = key
    return lookup


# =============================================================================
# Quick smoke-test when run directly
# =============================================================================

if __name__ == "__main__":
    print(f"EN vocabulary : {len(ISO_VOCABULARY_EN)} terms")
    print(f"FR vocabulary : {len(ISO_VOCABULARY_FR)} terms")

    total_en = sum(len(e["forms"]) for e in ISO_VOCABULARY_EN.values())
    total_fr = sum(len(e["forms"]) for e in ISO_VOCABULARY_FR.values())
    print(f"EN total surface forms : {total_en}")
    print(f"FR total surface forms : {total_fr}")

    # Count per standard
    for std in ("ISO9001", "ISO14001", "ISO45001", "ISO22000"):
        n_en = sum(1 for e in ISO_VOCABULARY_EN.values() if std in e["standards"])
        n_fr = sum(1 for e in ISO_VOCABULARY_FR.values() if std in e["standards"])
        print(f"  {std} — EN: {n_en} terms  |  FR: {n_fr} terms")

    # Scoped lookup demo
    print("\n--- ISO9001-only EN lookup (first 5 keys) ---")
    lk9001 = build_lookup(ISO_VOCABULARY_EN, ["ISO9001"])
    for k in list(lk9001.keys())[:5]:
        print(f"  '{k}' → '{lk9001[k]}'")

    print("\n--- ISO14001-only FR lookup (first 5 keys) ---")
    lk14001 = build_lookup(ISO_VOCABULARY_FR, ["ISO14001"])
    for k in list(lk14001.keys())[:5]:
        print(f"  '{k}' → '{lk14001[k]}'")

    print("\n--- Cross-standard check ---")
    print("'système de management environnemental' in ISO9001 EN lookup?",
          "système de management environnemental" in build_lookup(ISO_VOCABULARY_EN, ["ISO9001"]))
    print("'système de management environnemental' in ISO14001 EN lookup?",
          "système de management environnemental" in build_lookup(ISO_VOCABULARY_EN, ["ISO14001"]))