"""
vocabulary.py
=============
ISO QHSE Vocabulary for RAG / NLP scanning — QALITAS Project

Two flat dictionaries:
    ISO_VOCABULARY_EN  —  English surface forms
    ISO_VOCABULARY_FR  —  French surface forms

Format
------
    key   = canonical term (primary match surface)
    value = list[str] of all surface forms to scan for
              (the key itself is always included as first element)

Sources: ISO 9001:2015 (EN), ISO 14001:2015 (FR)
"""

# =============================================================================
# ENGLISH vocabulary
# key = canonical English term
# value = all English surface forms (including abbreviations & variations)
# =============================================================================

ISO_VOCABULARY_EN: dict[str, list[str]] = {

    # --- Leadership & Governance ---

    "top management": [
        "top management",
        "senior management",
        "leadership",
        "upper management",
        "executive management",
        "executive team",
        "governing body",
    ],

    "management review": [
        "management review",
        "management review meeting",
        "system review",
        "review by management",
        "periodic management review",
        "annual management review",
    ],

    "quality policy": [
        "quality policy",
        "quality statement",
        "quality commitment",
        "quality declaration",
        "policy for quality",
    ],

    "environmental policy": [
        "environmental policy",
        "environmental commitment",
        "environmental statement",
        "environmental declaration",
        "policy for environment",
    ],

    "quality management system": [
        "quality management system",
        "QMS",
        "quality system",
        "management system for quality",
    ],

    "environmental management system": [
        "environmental management system",
        "EMS",
        "environmental system",
        "management system for environment",
    ],

    "organizational roles and responsibilities": [
        "organizational roles and responsibilities",
        "roles and responsibilities",
        "roles responsibilities and authorities",
        "responsibility assignment",
        "authority assignment",
        "accountability",
    ],

    "leadership and commitment": [
        "leadership and commitment",
        "management commitment",
        "top management commitment",
        "demonstration of leadership",
        "commitment of management",
    ],

    "customer focus": [
        "customer focus",
        "customer orientation",
        "customer requirements",
        "customer needs",
        "customer expectations",
        "focus on customer",
    ],

    "interested parties": [
        "interested parties",
        "stakeholders",
        "relevant parties",
        "concerned parties",
        "external parties",
        "internal parties",
    ],

    # --- Context ---

    "context of the organization": [
        "context of the organization",
        "organizational context",
        "internal and external issues",
        "internal issues",
        "external issues",
        "understanding the organization",
        "understanding the context",
    ],

    "scope": [
        "scope",
        "scope of the management system",
        "scope of the QMS",
        "scope of the EMS",
        "system boundaries",
        "applicability",
    ],

    # --- Planning ---

    "risks and opportunities": [
        "risks and opportunities",
        "risk and opportunity",
        "threats and opportunities",
        "risks opportunities",
        "actions to address risks",
    ],

    "risk": [
        "risk",
        "risks",
        "risk assessment",
        "risk analysis",
        "risk evaluation",
        "risk identification",
        "risk management",
    ],

    "risk-based thinking": [
        "risk-based thinking",
        "risk based thinking",
        "risk-based approach",
        "preventive approach",
        "preventive thinking",
    ],

    "objectives": [
        "objectives",
        "quality objectives",
        "environmental objectives",
        "targets",
        "goals",
        "key results",
        "intended results",
    ],

    "planning of changes": [
        "planning of changes",
        "change management",
        "change planning",
        "change control",
        "management of change",
        "planned changes",
        "unintended changes",
    ],

    "actions to address risks and opportunities": [
        "actions to address risks and opportunities",
        "risk treatment",
        "risk mitigation",
        "preventive actions",
        "opportunity actions",
    ],

    "compliance obligations": [
        "compliance obligations",
        "legal requirements",
        "regulatory requirements",
        "legal and other requirements",
        "statutory requirements",
        "applicable requirements",
        "binding obligations",
    ],

    "environmental aspects": [
        "environmental aspects",
        "significant environmental aspects",
        "environmental elements",
        "environmental interactions",
    ],

    "environmental impact": [
        "environmental impact",
        "environmental impacts",
        "environmental effect",
        "environmental consequence",
        "impact on the environment",
    ],

    "life cycle perspective": [
        "life cycle perspective",
        "life cycle",
        "lifecycle",
        "life cycle thinking",
        "life cycle assessment",
        "LCA",
        "cradle to grave",
        "end of life",
    ],

    "pollution prevention": [
        "pollution prevention",
        "prevent pollution",
        "emission control",
        "waste reduction",
        "emission reduction",
        "reduction at source",
    ],

    "emergency preparedness": [
        "emergency preparedness",
        "emergency preparedness and response",
        "emergency response",
        "emergency plan",
        "contingency plan",
        "crisis management",
        "incident response",
    ],

    # --- Support ---

    "documented information": [
        "documented information",
        "documents",
        "records",
        "documentation",
        "documented procedures",
        "quality manual",
        "documented evidence",
    ],

    "maintain documented information": [
        "maintain documented information",
        "maintain documentation",
        "keep up to date",
        "document maintenance",
    ],

    "retain documented information": [
        "retain documented information",
        "retain records",
        "evidence retention",
        "archiving",
        "record retention",
        "objective evidence",
    ],

    "control of documented information": [
        "control of documented information",
        "document control",
        "documentation control",
        "version control",
        "document management",
    ],

    "competence": [
        "competence",
        "competences",
        "competencies",
        "qualification",
        "skills",
        "knowledge and skills",
        "ability",
        "expertise",
    ],

    "awareness": [
        "awareness",
        "awareness training",
        "personnel awareness",
        "staff awareness",
        "raising awareness",
    ],

    "communication": [
        "communication",
        "internal communication",
        "external communication",
        "communicating",
        "information sharing",
        "reporting",
    ],

    "resources": [
        "resources",
        "human resources",
        "infrastructure",
        "financial resources",
        "provision of resources",
        "resource management",
    ],

    "infrastructure": [
        "infrastructure",
        "facilities",
        "equipment",
        "buildings",
        "hardware",
        "software",
        "utilities",
    ],

    "organizational knowledge": [
        "organizational knowledge",
        "organisation knowledge",
        "knowledge management",
        "lessons learned",
        "knowledge base",
        "institutional knowledge",
    ],

    "training": [
        "training",
        "education",
        "professional development",
        "staff training",
        "employee training",
    ],

    # --- Operation ---

    "operational planning and control": [
        "operational planning and control",
        "operational control",
        "process control",
        "operational planning",
        "operations management",
        "control of operations",
    ],

    "process approach": [
        "process approach",
        "process management",
        "process mapping",
        "process interactions",
        "manage processes",
    ],

    "PDCA": [
        "PDCA",
        "plan do check act",
        "plan-do-check-act",
        "Deming cycle",
        "PDSA",
        "plan check act",
    ],

    "design and development": [
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

    "requirements for products and services": [
        "requirements for products and services",
        "product requirements",
        "service requirements",
        "customer requirements",
        "product and service requirements",
    ],

    "production and service provision": [
        "production and service provision",
        "service provision",
        "production",
        "manufacturing",
        "service delivery",
        "controlled conditions",
    ],

    "control of external providers": [
        "control of external providers",
        "external providers",
        "supplier control",
        "vendor management",
        "supplier evaluation",
        "purchasing control",
        "control of outsourcing",
    ],

    "outsourcing": [
        "outsourcing",
        "outsourced processes",
        "external provision",
        "subcontracting",
        "third-party processes",
    ],

    "identification and traceability": [
        "identification and traceability",
        "traceability",
        "product identification",
        "batch number",
        "lot number",
        "tracking",
    ],

    "nonconforming outputs": [
        "nonconforming outputs",
        "control of nonconforming outputs",
        "nonconforming products",
        "nonconforming services",
        "defective outputs",
    ],

    "release of products and services": [
        "release of products and services",
        "product release",
        "service release",
        "acceptance criteria",
        "release criteria",
    ],

    # --- Performance Evaluation ---

    "monitoring and measurement": [
        "monitoring and measurement",
        "monitoring",
        "measurement",
        "surveillance",
        "performance measurement",
        "measuring",
    ],

    "analysis and evaluation": [
        "analysis and evaluation",
        "data analysis",
        "evaluation",
        "results analysis",
        "trend analysis",
        "statistical analysis",
    ],

    "customer satisfaction": [
        "customer satisfaction",
        "customer feedback",
        "customer perception",
        "customer complaints",
        "satisfaction survey",
        "NPS",
        "CSAT",
    ],

    "internal audit": [
        "internal audit",
        "internal audits",
        "audit programme",
        "audit program",
        "audit schedule",
        "first-party audit",
        "audit findings",
        "audit criteria",
    ],

    "performance evaluation": [
        "performance evaluation",
        "system effectiveness",
        "evaluate performance",
        "performance assessment",
        "evaluate effectiveness",
    ],

    "environmental performance": [
        "environmental performance",
        "environmental results",
        "environmental KPIs",
        "environmental indicators",
        "environmental performance indicators",
    ],

    "compliance evaluation": [
        "compliance evaluation",
        "evaluate compliance",
        "compliance check",
        "conformity assessment",
        "compliance verification",
        "compliance status",
    ],

    "indicator": [
        "indicator",
        "indicators",
        "KPI",
        "KPIs",
        "key performance indicator",
        "performance indicator",
        "measurement indicator",
    ],

    # --- Improvement ---

    "continual improvement": [
        "continual improvement",
        "continuous improvement",
        "ongoing improvement",
        "improvement process",
        "kaizen",
        "improvement cycle",
    ],

    "corrective action": [
        "corrective action",
        "corrective actions",
        "CAPA",
        "CAR",
        "root cause analysis",
        "root cause correction",
        "corrective measure",
    ],

    "nonconformity": [
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

    "conformity": [
        "conformity",
        "conformance",
        "compliance",
        "fulfilment of requirements",
        "meeting requirements",
    ],

    "improvement": [
        "improvement",
        "improvements",
        "improve",
        "performance improvement",
        "system improvement",
        "breakthrough",
        "innovation",
    ],

    "requirement": [
        "requirement",
        "requirements",
        "specified requirement",
        "implied requirement",
        "obligatory requirement",
        "criterion",
    ],
}


# =============================================================================
# FRENCH vocabulary
# key = canonical French term
# value = all French surface forms (including abbreviations & variations)
# =============================================================================

ISO_VOCABULARY_FR: dict[str, list[str]] = {

    # --- Leadership & Gouvernance ---

    "direction": [
        "direction",
        "haute direction",
        "dirigeants",
        "encadrement supérieur",
        "équipe de direction",
        "responsables",
    ],

    "revue de direction": [
        "revue de direction",
        "revue de management",
        "revue du système de management",
        "bilan de direction",
        "revue annuelle",
        "revue périodique",
    ],

    "politique qualité": [
        "politique qualité",
        "politique de qualité",
        "déclaration qualité",
        "engagement qualité",
        "orientations qualité",
    ],

    "politique environnementale": [
        "politique environnementale",
        "politique en matière d'environnement",
        "engagement environnemental",
        "déclaration environnementale",
        "orientations environnementales",
    ],

    "système de management de la qualité": [
        "système de management de la qualité",
        "SMQ",
        "système qualité",
        "système de management qualité",
    ],

    "système de management environnemental": [
        "système de management environnemental",
        "SME",
        "système environnemental",
        "système de management de l'environnement",
    ],

    "rôles responsabilités et autorités": [
        "rôles responsabilités et autorités",
        "rôles et responsabilités",
        "responsabilités et autorités",
        "attribution des responsabilités",
        "délégation d'autorité",
    ],

    "leadership et engagement": [
        "leadership et engagement",
        "engagement de la direction",
        "implication de la direction",
        "démonstration du leadership",
        "engagement managérial",
    ],

    "orientation client": [
        "orientation client",
        "focus client",
        "besoins des clients",
        "attentes des clients",
        "exigences des clients",
        "satisfaction client",
    ],

    "parties intéressées": [
        "parties intéressées",
        "parties prenantes",
        "parties concernées",
        "parties pertinentes",
        "tiers concernés",
    ],

    # --- Contexte ---

    "contexte de l'organisme": [
        "contexte de l'organisme",
        "contexte organisationnel",
        "enjeux internes et externes",
        "enjeux internes",
        "enjeux externes",
        "compréhension de l'organisme",
    ],

    "domaine d'application": [
        "domaine d'application",
        "périmètre",
        "champ d'application",
        "limites du système",
        "applicabilité",
    ],

    # --- Planification ---

    "risques et opportunités": [
        "risques et opportunités",
        "risques et opportunites",
        "menaces et opportunités",
        "opportunités et risques",
        "actions face aux risques",
    ],

    "risque": [
        "risque",
        "risques",
        "analyse des risques",
        "évaluation des risques",
        "identification des risques",
        "gestion des risques",
        "management des risques",
    ],

    "approche par les risques": [
        "approche par les risques",
        "réflexion fondée sur le risque",
        "pensée basée sur les risques",
        "approche préventive",
        "approche risque",
    ],

    "objectifs": [
        "objectifs",
        "objectifs qualité",
        "objectifs environnementaux",
        "cibles",
        "buts",
        "résultats attendus",
        "résultats escomptés",
    ],

    "planification des modifications": [
        "planification des modifications",
        "gestion des changements",
        "maîtrise des modifications",
        "management du changement",
        "modifications planifiées",
        "changements planifiés",
    ],

    "actions face aux risques et opportunités": [
        "actions face aux risques et opportunités",
        "actions à mettre en œuvre face aux risques",
        "traitement des risques",
        "atténuation des risques",
        "actions préventives",
    ],

    "obligations de conformité": [
        "obligations de conformité",
        "exigences légales",
        "exigences réglementaires",
        "exigences légales et autres exigences",
        "exigences applicables",
        "obligations réglementaires",
        "conformité réglementaire",
    ],

    "aspects environnementaux": [
        "aspects environnementaux",
        "aspects environnementaux significatifs",
        "AES",
        "aspects significatifs",
        "éléments environnementaux",
    ],

    "impact environnemental": [
        "impact environnemental",
        "impacts environnementaux",
        "effets sur l'environnement",
        "conséquences environnementales",
        "incidence environnementale",
    ],

    "perspective de cycle de vie": [
        "perspective de cycle de vie",
        "cycle de vie",
        "analyse du cycle de vie",
        "ACV",
        "approche cycle de vie",
        "du berceau à la tombe",
    ],

    "prévention de la pollution": [
        "prévention de la pollution",
        "prévenir la pollution",
        "réduction des émissions",
        "lutte contre la pollution",
        "réduction à la source",
        "contrôle des émissions",
    ],

    "préparation aux situations d'urgence": [
        "préparation aux situations d'urgence",
        "situations d'urgence",
        "préparation et réponse aux situations d'urgence",
        "réponse aux urgences",
        "plan d'urgence",
        "plan d'intervention",
        "gestion des crises",
    ],

    # --- Support ---

    "informations documentées": [
        "informations documentées",
        "information documentée",
        "documents",
        "enregistrements",
        "documentation",
        "procédures documentées",
        "manuel qualité",
        "preuves documentées",
    ],

    "tenir à jour les informations documentées": [
        "tenir à jour les informations documentées",
        "tenir à jour",
        "maintenir à jour",
        "mise à jour de la documentation",
        "maintenir la documentation",
    ],

    "conserver les informations documentées": [
        "conserver les informations documentées",
        "conserver les enregistrements",
        "conservation des preuves",
        "archivage",
        "conservation des enregistrements",
        "preuves objectives",
    ],

    "maîtrise des informations documentées": [
        "maîtrise des informations documentées",
        "maîtrise documentaire",
        "contrôle des documents",
        "gestion documentaire",
        "contrôle des versions",
        "management documentaire",
    ],

    "compétence": [
        "compétence",
        "compétences",
        "qualification",
        "aptitude",
        "savoir-faire",
        "habilitation",
        "expertise",
    ],

    "sensibilisation": [
        "sensibilisation",
        "prise de conscience",
        "formation sensibilisation",
        "sensibiliser le personnel",
        "conscience professionnelle",
    ],

    "communication": [
        "communication",
        "communication interne",
        "communication externe",
        "diffusion de l'information",
        "partage d'information",
        "reporting",
    ],

    "ressources": [
        "ressources",
        "ressources humaines",
        "infrastructure",
        "ressources financières",
        "provision de ressources",
        "gestion des ressources",
        "moyens",
    ],

    "infrastructure": [
        "infrastructure",
        "installations",
        "équipements",
        "bâtiments",
        "matériels",
        "logiciels",
        "moyens matériels",
    ],

    "connaissances organisationnelles": [
        "connaissances organisationnelles",
        "gestion des connaissances",
        "retour d'expérience",
        "REX",
        "capitalisation des connaissances",
        "base de connaissances",
    ],

    "formation": [
        "formation",
        "formation professionnelle",
        "développement des compétences",
        "formation du personnel",
        "plan de formation",
    ],

    # --- Réalisation ---

    "planification et maîtrise opérationnelles": [
        "planification et maîtrise opérationnelles",
        "maîtrise opérationnelle",
        "contrôle opérationnel",
        "planification opérationnelle",
        "maîtrise des activités",
    ],

    "approche processus": [
        "approche processus",
        "gestion par processus",
        "management des processus",
        "cartographie des processus",
        "interactions entre processus",
    ],

    "PDCA": [
        "PDCA",
        "Planifier Réaliser Vérifier Agir",
        "roue de Deming",
        "cycle PDCA",
        "amélioration itérative",
    ],

    "conception et développement": [
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

    "exigences relatives aux produits et services": [
        "exigences relatives aux produits et services",
        "exigences produits",
        "exigences services",
        "exigences applicables aux produits",
    ],

    "réalisation des activités opérationnelles": [
        "réalisation des activités opérationnelles",
        "réalisation des activités",
        "prestation de services",
        "production",
        "fabrication",
        "exécution des activités",
    ],

    "maîtrise des fournisseurs externes": [
        "maîtrise des fournisseurs externes",
        "fournisseurs externes",
        "maîtrise des prestataires",
        "évaluation des fournisseurs",
        "sélection des fournisseurs",
        "achats",
        "contrôle des sous-traitants",
    ],

    "externalisation": [
        "externalisation",
        "processus externalisés",
        "sous-traitance",
        "prestataires",
        "tiers",
        "activités externalisées",
    ],

    "identification et traçabilité": [
        "identification et traçabilité",
        "traçabilité",
        "identification du produit",
        "numéro de lot",
        "numéro de série",
        "suivi",
    ],

    "éléments de sortie non conformes": [
        "éléments de sortie non conformes",
        "produits non conformes",
        "services non conformes",
        "sorties non conformes",
        "maîtrise des non-conformités",
    ],

    "libération des produits et services": [
        "libération des produits et services",
        "libération du produit",
        "critères d'acceptation",
        "autorisation de livraison",
    ],

    # --- Évaluation des performances ---

    "surveillance et mesure": [
        "surveillance et mesure",
        "surveillance",
        "mesure",
        "suivi",
        "mesure des performances",
        "surveillance des performances",
    ],

    "analyse et évaluation": [
        "analyse et évaluation",
        "analyse des données",
        "évaluation",
        "analyse des résultats",
        "analyse de tendances",
        "analyse statistique",
    ],

    "satisfaction du client": [
        "satisfaction du client",
        "satisfaction client",
        "perception du client",
        "réclamations clients",
        "retour client",
        "enquête de satisfaction",
    ],

    "audit interne": [
        "audit interne",
        "audits internes",
        "programme d'audit",
        "programme d'audit interne",
        "calendrier d'audit",
        "audit de première partie",
        "résultats d'audit",
        "critères d'audit",
    ],

    "évaluation des performances": [
        "évaluation des performances",
        "évaluation de l'efficacité du système",
        "mesure des résultats",
        "évaluation du système",
    ],

    "performance environnementale": [
        "performance environnementale",
        "résultats environnementaux",
        "indicateurs environnementaux",
        "indicateurs de performance environnementale",
    ],

    "évaluation de la conformité": [
        "évaluation de la conformité",
        "vérification de la conformité",
        "bilan de conformité",
        "état de conformité",
        "contrôle de conformité",
        "conformité aux obligations",
    ],

    "indicateur": [
        "indicateur",
        "indicateurs",
        "indicateur de performance",
        "indicateurs clés",
        "KPI",
        "tableau de bord",
        "mesure",
    ],

    # --- Amélioration ---

    "amélioration continue": [
        "amélioration continue",
        "amélioration permanente",
        "progrès continu",
        "démarche d'amélioration",
        "kaizen",
        "amélioration itérative",
    ],

    "action corrective": [
        "action corrective",
        "actions correctives",
        "CAPA",
        "analyse des causes",
        "analyse des causes racines",
        "correction",
        "mesure corrective",
        "plan d'action correctif",
    ],

    "non-conformité": [
        "non-conformité",
        "non-conformités",
        "NC",
        "écart",
        "défaut de conformité",
        "anomalie",
        "défaillance",
        "non-respect des exigences",
    ],

    "conformité": [
        "conformité",
        "respect des exigences",
        "satisfaction des exigences",
        "être conforme",
    ],

    "amélioration": [
        "amélioration",
        "améliorations",
        "améliorer",
        "amélioration des performances",
        "progrès",
        "optimisation",
        "gains",
    ],

    "exigence": [
        "exigence",
        "exigences",
        "besoin",
        "attente",
        "obligation",
        "critère",
        "prescription",
    ],
}


# =============================================================================
# Quick smoke-test when run directly
# =============================================================================

if __name__ == "__main__":
    print(f"EN vocabulary: {len(ISO_VOCABULARY_EN)} terms")
    print(f"FR vocabulary: {len(ISO_VOCABULARY_FR)} terms")

    total_en = sum(len(v) for v in ISO_VOCABULARY_EN.values())
    total_fr = sum(len(v) for v in ISO_VOCABULARY_FR.values())
    print(f"EN total surface forms: {total_en}")
    print(f"FR total surface forms: {total_fr}")

    print("\nSample — EN 'compliance obligations':")
    print(ISO_VOCABULARY_EN["compliance obligations"])

    print("\nSample — FR 'obligations de conformité':")
    print(ISO_VOCABULARY_FR["obligations de conformité"])