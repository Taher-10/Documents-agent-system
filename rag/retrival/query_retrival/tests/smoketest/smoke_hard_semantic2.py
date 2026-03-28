"""
smoke_hard_summary_agent2_fr.py
────────────────────────────────────────────────────────────────────────────
Cas de test Agent 2 (Conformité Normative) – format smoke_hard_semantic
Traduit en français · ISO 9001:2015 · Manuel EQMS Spotless (26 pages)

50 cas répartis en 4 niveaux :
  • Tier 1 – Facile  (01-10) : clause unique, signal clair
  • Tier 2 – Moyen   (11-20) : couverture partielle, références croisées
  • Tier 3 – Difficile (21-35): sections manquantes, multi-clause, verbes
  • Tier 4 – Expert  (36-50) : multi-référentiel, cas limites

Run:
    python rag/retrival/query_retrival/tests/smoketest/smoke_hard_summary_agent2_fr.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass
from typing import List, Optional

import requests
from qdrant_client import QdrantClient

from rag.retrival.models import TransformedQuery, RetrievedChunk
from rag.retrival.query_retrival.retriever_dense import DenseRetriever, EmptyCorpusError as DenseEmptyCorpusError
from rag.retrival.query_retrival.retriever import HybridRetriever, EmptyCorpusError as HybridEmptyCorpusError
from rag.retrival.query_transformer.Querytransformer import transform


# ── Config ────────────────────────────────────────────────────────────────────

QDRANT_HOST  = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT  = int(os.getenv("QDRANT_PORT", "6333"))
OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
LANGUAGE     = "FR"
NORM_FILTER  = ["ISO9001"]
RETRIEVE_K   = 10
RECALL_K     = 10


# ── TestCase ──────────────────────────────────────────────────────────────────

@dataclass
class TestCase:
    name: str
    query: str
    expected_any: List[str]
    top_k_pass: int
    difficulty: str
    fmt: str


# ═════════════════════════════════════════════════════════════════════════════
# TIER 1 – FACILE (01-10)
# Clause unique, signal clair, sujets bien couverts par le manuel EQMS Spotless
# ═════════════════════════════════════════════════════════════════════════════

TESTS: List[TestCase] = [

# ── 01 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="01. 4.4 Détection du type de document – Manuel EQMS",
    query=(
        "Identifiez le type de ce document :\n\n"
        "Manuel du Système de Management Environnemental et Qualité (EQMS)\n"
        "ISO 9001:2015 & ISO 14001:2015\n"
        "Spotless a développé et mis en œuvre un Système de Management "
        "Environnemental et Qualité (EQMS) intégré, s'appuyant sur les "
        "référentiels ISO 9001:2015 et ISO 14001:2015."
    ),
    expected_any=["4.4"],
    top_k_pass=10,
    difficulty="easy",
    fmt="document_type_detection",
),

# ── 02 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="02. 4.1 Contexte de l'organisme – vérification de conformité",
    query=(
        "4.1 Contexte organisationnel\n"
        "Spotless s'engage à définir sa position sur le marché et à comprendre "
        "comment les facteurs juridiques, politiques, économiques, sociaux et "
        "technologiques influencent son orientation stratégique et son contexte "
        "organisationnel. Spotless identifie, analyse, surveille et révise les "
        "facteurs susceptibles d'affecter sa capacité à satisfaire ses clients "
        "et parties prenantes."
    ),
    expected_any=["4.1"],
    top_k_pass=10,
    difficulty="easy",
    fmt="section_extract",
),

# ── 03 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="03. 4.3 Déclaration du domaine d'application – présent et documenté",
    query=(
        "La déclaration du domaine d'application de l'EQMS est la suivante : "
        "'Notre Système de Management Environnemental et Qualité vise à soutenir "
        "la conception et la prestation de services de nettoyage contractuels et "
        "spécialisés depuis notre bureau de Cambridge.'\n"
        "Cette déclaration satisfait-elle à la clause 4.3 de l'ISO 9001:2015 ?"
    ),
    expected_any=["4.3"],
    top_k_pass=10,
    difficulty="easy",
    fmt="paragraph_conformity",
),

# ── 04 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="04. 5.2 Politique qualité – disponible en information documentée",
    query=(
        "Le manuel EQMS Spotless inclut-il la politique qualité en tant "
        "qu'information documentée, conformément à la clause 5.2 de "
        "l'ISO 9001:2015 ?"
    ),
    expected_any=["5.2"],
    top_k_pass=10,
    difficulty="easy",
    fmt="clause_question",
),

# ── 05 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="05. 7.1.2 Ressources humaines – fourniture des ressources",
    query=(
        "7.1.2 Ressources humaines\n"
        "Pour garantir la compétence de notre personnel, des fiches de poste ont "
        "été élaborées, précisant les qualifications, l'expérience et les "
        "responsabilités requises pour chaque poste ayant une incidence sur la "
        "conformité des produits et de l'EQMS."
    ),
    expected_any=["7.1.2"],
    top_k_pass=10,
    difficulty="easy",
    fmt="section_extract",
),

# ── 06 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="06. 9.2 Audit interne – programme décrit",
    query=(
        "Le programme d'audit de l'EQMS est coordonné par le Responsable EQMS, "
        "qui définit la fréquence et l'orientation générale de chaque audit "
        "interne. Le calendrier peut être modifié à tout moment afin de s'assurer "
        "que tous les domaines sont audités à une fréquence déterminée par le "
        "risque de non-conformité associé.\n\n"
        "Évaluer la conformité avec la clause 9.2 de l'ISO 9001:2015."
    ),
    expected_any=["9.2"],
    top_k_pass=10,
    difficulty="easy",
    fmt="paragraph_conformity",
),

# ── 07 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="07. 10.2 Non-conformité et action corrective – couverture de base",
    query=(
        "10.2 Non-conformité et action corrective\n"
        "Les non-conformités relatives aux exigences environnementales et "
        "qualité sont signalées au Responsable EQMS afin qu'une investigation "
        "puisse être engagée. Le responsable concerné documente la non-conformité "
        "et analyse la cause profonde. Le Responsable EQMS enregistre le rapport "
        "ainsi que toute action corrective convenue."
    ),
    expected_any=["10.2"],
    top_k_pass=10,
    difficulty="easy",
    fmt="section_extract",
),

# ── 08 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="08. 6.2 Objectifs qualité – mesurabilité",
    query=(
        "La section 6.2 liste les indicateurs clés de performance (KPI) suivants : "
        "chiffre d'affaires et rentabilité, objectifs de vente, gains et pertes "
        "de contrats, déclarations d'accidents, répartition des effectifs. "
        "Ces objectifs sont-ils conformes à la clause 6.2 de l'ISO 9001 ?"
    ),
    expected_any=["6.2"],
    top_k_pass=10,
    difficulty="easy",
    fmt="clause_question",
),

# ── 09 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="09. 7.4 Communication – vérification de l'exhaustivité",
    query=(
        "Listez les éléments manquants dans l'approche de communication de "
        "l'EQMS Spotless par rapport à la clause 7.4 de l'ISO 9001:2015. "
        "Le manuel décrit la communication interne via des réunions, des "
        "formations, des tableaux d'affichage, des newsletters, et la "
        "communication externe via un tableau des parties prenantes."
    ),
    expected_any=["7.4"],
    top_k_pass=10,
    difficulty="easy",
    fmt="gap_analysis",
),

# ── 10 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="10. 4.2 Parties intéressées – besoins et attentes",
    query=(
        "4.2 Parties intéressées pertinentes\n"
        "Spotless reconnaît avoir un ensemble unique de parties intéressées dont "
        "les besoins et attentes évoluent au fil du temps, et que seul un sous-ensemble "
        "limité de leurs exigences respectives est applicable à nos opérations "
        "ou à notre EQMS."
    ),
    expected_any=["4.2"],
    top_k_pass=10,
    difficulty="easy",
    fmt="section_extract",
),


# ═════════════════════════════════════════════════════════════════════════════
# TIER 2 – MOYEN (11-20)
# Couverture partielle, exigences implicites, références croisées nécessaires
# ═════════════════════════════════════════════════════════════════════════════

# ── 11 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="11. 7.5.3 Maîtrise des informations documentées – vérification détaillée",
    query=(
        "Section 7.5 – Information documentée\n"
        "Spotless utilise des formulaires et modèles standards accessibles via un "
        "système en nuage. Un système électronique de gestion documentaire, sauvegardé "
        "et mis à jour selon les besoins, est utilisé pour conserver les informations "
        "documentées, garantissant que seules les versions en cours sont disponibles.\n\n"
        "Cependant, le manuel ne décrit pas comment les documents d'origine externe "
        "sont identifiés et maîtrisés, ni comment les enregistrements conservés sont "
        "protégés contre toute modification non intentionnelle."
    ),
    expected_any=["7.5.3"],
    top_k_pass=10,
    difficulty="medium",
    fmt="paragraph_non_conformity",
),

# ── 12 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="12. 5.1.1 Engagement de la direction – détection des verbes",
    query=(
        "Détectez tous les verbes d'engagement dans cette section et vérifiez "
        "que chacun est suivi d'une méthode de preuve :\n\n"
        "La direction de Spotless est responsable de la mise en œuvre de notre "
        "EQMS, y compris l'élaboration et le déploiement de nos politiques qualité "
        "et environnementales, ainsi que des objectifs et cibles associés. Nous "
        "assurons la responsabilité et la gouvernance de toutes les activités liées "
        "aux processus du cycle de vie. La direction est engagée dans la mise en "
        "œuvre et le développement de l'EQMS."
    ),
    expected_any=["5.1.1"],
    top_k_pass=10,
    difficulty="medium",
    fmt="verb_detection",
),

# ── 13 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="13. 8.2.3 Revue des exigences – revue préalable à l'acceptation",
    query=(
        "8.2.3 Revue des exigences\n"
        "Avant de s'engager auprès du client, Spotless s'assure et confirme "
        "sa capacité à fournir le service requis. Des revues préalables à "
        "l'acceptation sont menées pour garantir que : les exigences de service "
        "sont définies ; les exigences environnementales sont définies ; les "
        "exigences de support au service sont définies ; les exigences non "
        "formulées par le client mais nécessaires à l'usage prévu sont appropriées ; "
        "les exigences contractuelles différant de celles préalablement exprimées "
        "sont résolues ; Spotless a la capacité de satisfaire les exigences de "
        "service définies ; les informations documentées attestant des résultats "
        "de la revue sont conservées."
    ),
    expected_any=["8.2.3"],
    top_k_pass=10,
    difficulty="medium",
    fmt="section_extract",
),

# ── 14 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="14. 7.5 Information documentée – versions obsolètes utilisées (NC)",
    query=(
        "7.5 Information documentée\n"
        "Les procédures environnementales existent, cependant elles ne sont pas "
        "révisées régulièrement et certaines versions obsolètes restent utilisées "
        "au sein des opérations."
    ),
    expected_any=["7.5"],
    top_k_pass=10,
    difficulty="medium",
    fmt="paragraph_non_conformity",
),

# ── 15 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="15. 8.4.1 Maîtrise des prestataires externes – critères d'évaluation",
    query=(
        "Tracez les preuves relatives à la clause 8.4.1 (prestataires externes) "
        "dans le manuel EQMS Spotless :\n\n"
        "Chaque fournisseur est évalué selon des critères tels que la détention "
        "des certifications ISO 9001 et 14001 et la possession de politiques HSE "
        "adéquates. La performance et la capacité des fournisseurs existants et "
        "potentiels sont évaluées à l'aide du Questionnaire Fournisseur Agréé."
    ),
    expected_any=["8.4.1"],
    top_k_pass=10,
    difficulty="medium",
    fmt="evidence_trace",
),

# ── 16 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="16. 7.1.5 Ressources de surveillance et de mesure – étalonnage",
    query=(
        "7.1.5 Outils de surveillance et de mesure\n"
        "Spotless s'assure que tous les équipements de test PAT sont étalonnés "
        "chaque année. Les appareils de mesure TDS sont remplacés tous les 2 ans. "
        "Tous les enregistrements des équipements de l'entreprise sont stockés "
        "dans la base de données des équipements."
    ),
    expected_any=["7.1.5"],
    top_k_pass=10,
    difficulty="medium",
    fmt="section_extract",
),

# ── 17 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="17. 9.3.2 Revue de direction – exhaustivité des données d'entrée",
    query=(
        "Évaluer si les données d'entrée de la revue de direction de Spotless "
        "(section 9.3.2) couvrent tous les éléments requis par la clause 9.3.2 "
        "de l'ISO 9001:2015.\n\n"
        "Le manuel indique : 'Les principales données d'entrée examinées comprennent "
        "les données de conformité et de performance recueillies aux points de "
        "données qualité et environnementaux clés.'"
    ),
    expected_any=["9.3.2"],
    top_k_pass=10,
    difficulty="medium",
    fmt="gap_analysis",
),

# ── 18 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="18. 7.2 Compétences – évaluation de l'efficacité de la formation",
    query=(
        "La clause 7.2(c) de l'ISO 9001:2015 exige de mettre en œuvre des actions "
        "pour acquérir les compétences nécessaires et d'évaluer l'efficacité de "
        "ces actions. La section 7.1.2.1 du manuel EQMS Spotless satisfait-elle "
        "cette exigence ?\n\n"
        "Extrait : 'Si nécessaire, des formations aux compétences et un suivi sont "
        "réalisés en interne ; pour les compétences plus spécialisées, des séminaires "
        "ou formations externes sont utilisés. L'efficacité de la formation est "
        "évaluée et enregistrée.'"
    ),
    expected_any=["7.2"],
    top_k_pass=10,
    difficulty="medium",
    fmt="clause_question",
),

# ── 19 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="19. 8.5.1 Maîtrise de la prestation de service – conditions maîtrisées",
    query=(
        "La section 8.5.1 Maîtrise de la prestation de service précise que les "
        "conditions maîtrisées incluent : des contrôles qualité avec équipements "
        "de mesure, la manutention/stockage/transport, et des audits qualité de "
        "site réalisés.\n\n"
        "Cependant, la clause 8.5.1 de l'ISO 9001 exige plusieurs conditions "
        "maîtrisées supplémentaires. Identifiez ce qui manque."
    ),
    expected_any=["8.5.1"],
    top_k_pass=10,
    difficulty="medium",
    fmt="paragraph_non_conformity",
),

# ── 20 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="20. 6.3 Planification des modifications – mode maîtrisé",
    query=(
        "6.4 Planification des changements\n"
        "Lorsque des changements du système de management sont planifiés, la "
        "direction s'assure que tout le personnel est informé des changements "
        "affectant son processus, et qu'un suivi ultérieur est effectué pour "
        "garantir que les changements de l'EQMS sont efficacement mis en œuvre "
        "et n'affectent pas négativement les autres processus."
    ),
    expected_any=["6.3"],
    top_k_pass=10,
    difficulty="medium",
    fmt="section_extract",
),


# ═════════════════════════════════════════════════════════════════════════════
# TIER 3 – DIFFICILE (21-35)
# Sections manquantes, multi-clause, détection de verbes, raisonnement complexe
# ═════════════════════════════════════════════════════════════════════════════

# ── 21 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="21. 8.5.2 Identification et traçabilité – ABSENT",
    query=(
        "Le manuel EQMS Spotless ne contient pas de section sur "
        "l'identification et la traçabilité des sorties de service "
        "(ISO 9001 8.5.2). Réalisez une analyse des écarts et recommandez "
        "ce qui devrait être ajouté."
    ),
    expected_any=["8.5.2"],
    top_k_pass=10,
    difficulty="hard",
    fmt="gap_analysis",
),

# ── 22 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="22. 8.5.3 Propriété des clients – ABSENT",
    query=(
        "La clause 8.5.3 de l'ISO 9001:2015 exige d'exercer la diligence "
        "requise vis-à-vis des biens appartenant aux clients ou aux prestataires "
        "externes. Spotless intervient sur les locaux des clients. Que devrait "
        "inclure le manuel EQMS pour satisfaire cette clause ?"
    ),
    expected_any=["8.5.3"],
    top_k_pass=10,
    difficulty="hard",
    fmt="recommendation_request",
),

# ── 23 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="23. 8.5.4 Préservation – ABSENT",
    query=(
        "Évaluer si la clause 8.5.4 de l'ISO 9001 (Préservation) est traitée "
        "dans l'EQMS Spotless. Pour un service de nettoyage, la préservation "
        "peut s'appliquer aux produits chimiques, aux fournitures de nettoyage "
        "et aux biens des clients."
    ),
    expected_any=["8.5.4"],
    top_k_pass=10,
    difficulty="hard",
    fmt="gap_analysis",
),

# ── 24 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="24. 8.5.5 Activités après livraison – ABSENT",
    query=(
        "Le manuel EQMS aborde-t-il les activités après livraison conformément "
        "à la clause 8.5.5 de l'ISO 9001 ? Considérer que les services de "
        "nettoyage comportent des aspects après livraison tels que les inspections "
        "de suivi et les périodes de garantie."
    ),
    expected_any=["8.5.5"],
    top_k_pass=10,
    difficulty="hard",
    fmt="gap_analysis",
),

# ── 25 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="25. 8.5.6 Maîtrise des modifications – changements de production/service",
    query=(
        "La clause 8.5.6 de l'ISO 9001 exige de revoir et maîtriser les "
        "modifications relatives à la production ou à la prestation de service. "
        "Le manuel EQMS traite de la planification des modifications au niveau "
        "du système de management (section 6.4), mais aborde-t-il les "
        "modifications opérationnelles au niveau de la prestation de service ?"
    ),
    expected_any=["8.5.6"],
    top_k_pass=10,
    difficulty="hard",
    fmt="clause_question",
),

# ── 26 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="26. 8.6 Libération des produits et services – ABSENT",
    query=(
        "Le manuel EQMS ne dispose pas de section dédiée à la libération des "
        "produits et services (ISO 9001 8.6). Évaluez l'écart."
    ),
    expected_any=["8.6"],
    top_k_pass=10,
    difficulty="hard",
    fmt="gap_analysis",
),

# ── 27 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="27. Multi-clause : 5.1.1 + 5.1.2 + 5.2 – package leadership",
    query=(
        "Évaluez simultanément la section 5 de l'EQMS Spotless (Leadership et "
        "Gouvernance) par rapport aux clauses 5.1.1 (leadership général), "
        "5.1.2 (orientation client) et 5.2 (politique) de l'ISO 9001. "
        "Produisez une matrice de couverture."
    ),
    expected_any=["5.1.1", "5.1.2", "5.2"],
    top_k_pass=10,
    difficulty="hard",
    fmt="multi_clause_matrix",
),

# ── 28 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="28. Référence croisée : 4.2 satisfait via le tableau 5.3.2",
    query=(
        "La section 4.2 (Parties intéressées) ne liste pas de parties spécifiques. "
        "Cependant, la section 5.3.2 contient un tableau : Clients, Propriétaires/"
        "actionnaires, Fournisseurs, Autorités réglementaires et statutaires, Public "
        "– avec besoins/attentes et modes de communication. Cette référence croisée "
        "satisfait-elle la clause 4.2 de l'ISO 9001 ?"
    ),
    expected_any=["4.2"],
    top_k_pass=10,
    difficulty="hard",
    fmt="cross_reference",
),

# ── 29 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="29. Scénario de sévérité : 9.1.2 Satisfaction client – 3 niveaux",
    query=(
        "Évaluez la même section à trois niveaux de sévérité :\n\n"
        "'L'entreprise réalise régulièrement des enquêtes de satisfaction client "
        "via un formulaire Google Docs. Les résultats sont compilés dans un tableau "
        "et les tendances sont discutées lors de la réunion mensuelle de direction.'\n\n"
        "Niveau 1 : Auto-évaluation\n"
        "Niveau 2 : Audit interne\n"
        "Niveau 3 : Audit externe (organisme certificateur)"
    ),
    expected_any=["9.1.2"],
    top_k_pass=10,
    difficulty="hard",
    fmt="severity_scenario",
),

# ── 30 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="30. 7.3 Sensibilisation – implications des non-conformités",
    query=(
        "7.1.2.2 Sensibilisation\n"
        "Tous les employés sont formés sur la pertinence et l'importance de leurs "
        "activités et sur la façon dont ils contribuent à la réalisation de nos "
        "politiques et objectifs. Nous cherchons à renforcer la sensibilisation "
        "à la qualité et à l'environnement par des communications régulières au "
        "personnel et lors des réunions de direction."
    ),
    expected_any=["7.3"],
    top_k_pass=10,
    difficulty="hard",
    fmt="section_extract",
),

# ── 31 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="31. 4.4 Processus du SMQ – exigences de détermination",
    query=(
        "La clause 4.4.1 de l'ISO 9001 exige que l'organisme détermine les "
        "processus nécessaires au SMQ, incluant : entrées/sorties, séquence/"
        "interactions, critères/méthodes/indicateurs, ressources, responsabilités, "
        "risques et évaluation/amélioration. L'EQMS Spotless définit-il "
        "adéquatement ses processus conformément à la clause 4.4 ?"
    ),
    expected_any=["4.4"],
    top_k_pass=10,
    difficulty="hard",
    fmt="clause_question",
),

# ── 32 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="32. 8.7 Maîtrise des sorties non conformes – exhaustivité",
    query=(
        "Tracez les exigences de la clause 8.7 de l'ISO 9001 par rapport "
        "à la section 8.6 :\n\n"
        "'Toute sortie de service non conforme aux exigences est correctement "
        "identifiée et maîtrisée pour éviter toute utilisation non intentionnelle. "
        "La non-conformité est analysée et ses causes sont investiguées. Des "
        "actions d'amélioration sont mises en œuvre. Les informations documentées "
        "relatives à la nature des non-conformités, à l'autorité de résolution "
        "et aux actions correctives en résultant sont conservées.'"
    ),
    expected_any=["8.7"],
    top_k_pass=10,
    difficulty="hard",
    fmt="evidence_trace",
),

# ── 33 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="33. 8.3 Conception et développement – applicabilité aux services",
    query=(
        "Spotless inclut une section complète sur la Conception et le Développement "
        "(8.3) dans son manuel EQMS. Pour une entreprise de nettoyage commercial, "
        "un processus complet de C&D est-il approprié ? Évaluez si le contenu est "
        "proportionné ou si une approche simplifiée avec justification selon 4.3 "
        "suffirait."
    ),
    expected_any=["8.3", "4.3"],
    top_k_pass=10,
    difficulty="hard",
    fmt="clause_question",
),

# ── 34 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="34. 9.1.3 Analyse et évaluation – exhaustivité de l'analyse des données",
    query=(
        "La clause 9.1.3 de l'ISO 9001 exige que les résultats d'analyse évaluent "
        "7 domaines spécifiques (a à g). Évaluez si la section 9.1.3 de l'EQMS "
        "Spotless les couvre tous :\n\n"
        "'Spotless surveille et analyse les tendances en utilisant : les "
        "caractéristiques des processus/services, la conformité aux exigences, "
        "les données de satisfaction client, les données fournisseurs, les résultats "
        "des actions sur risques/opportunités, l'efficacité de la planification IMS, "
        "les opportunités d'amélioration issues des audits/revues.'"
    ),
    expected_any=["9.1.3"],
    top_k_pass=10,
    difficulty="hard",
    fmt="gap_analysis",
),

# ── 35 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="35. Multi-clause : évaluation complète de la clause 7 – Support",
    query=(
        "Réalisez une évaluation complète de la section 7 de l'EQMS (Support) "
        "par rapport à toutes les sous-clauses de la clause 7 de l'ISO 9001 : "
        "7.1.1 à 7.1.6, 7.2, 7.3, 7.4, 7.5.1, 7.5.2, 7.5.3. "
        "Produisez une matrice de couverture consolidée."
    ),
    expected_any=["7.1.1", "7.1.2", "7.1.3", "7.1.4", "7.1.5", "7.1.6",
                  "7.2", "7.3", "7.4", "7.5"],
    top_k_pass=10,
    difficulty="hard",
    fmt="multi_clause_matrix",
),


# ═════════════════════════════════════════════════════════════════════════════
# TIER 4 – EXPERT (36-50)
# Multi-référentiel, contextuel, cas limites, scénarios avancés
# ═════════════════════════════════════════════════════════════════════════════

# ── 36 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="36. 7.5 / 9.3 / 10.3 Analyse de l'ancienneté du document – manuel daté 2016",
    query=(
        "Le manuel EQMS a été rédigé le 07/10/2016 et approuvé par Magda Lamming. "
        "Le tableau des modifications est vide – aucune révision depuis la première "
        "émission. Évaluez les implications en termes de conformité."
    ),
    expected_any=["7.5", "9.3", "10.3"],
    top_k_pass=10,
    difficulty="expert",
    fmt="evidence_trace",
),

# ── 37 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="37. 6.1 Risques spécifiques au secteur nettoyage – non traités",
    query=(
        "Spotless est une entreprise de nettoyage commercial. La clause 6.1 de "
        "l'ISO 9001 exige de traiter les risques et opportunités. Identifiez les "
        "risques spécifiques au secteur que l'EQMS devrait aborder mais ne "
        "couvre pas explicitement."
    ),
    expected_any=["6.1"],
    top_k_pass=10,
    difficulty="expert",
    fmt="recommendation_request",
),

# ── 38 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="38. 7.5.2 / 7.5.3 Incohérence de numérotation entre TdM et corps du texte",
    query=(
        "Le manuel EQMS présente une incohérence dans sa numérotation : la table "
        "des matières liste '5.5 RÔLES, RESPONSABILITÉS ET AUTORITÉS' et "
        "'5.6 COMMUNICATION', tandis que le corps du texte utilise '5.2 Rôles, "
        "Responsabilités et Autorités' et '5.3 Communication'. Évaluez cela comme "
        "un problème de maîtrise des informations documentées."
    ),
    expected_any=["7.5.2", "7.5.3"],
    top_k_pass=10,
    difficulty="expert",
    fmt="evidence_trace",
),

# ── 39 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="39. 5.3 Rôles et responsabilités – autorité spécifique au SMQ",
    query=(
        "Analysez les verbes d'engagement et les responsabilités assignées :\n\n"
        "'La direction doit attribuer la responsabilité et l'autorité pour : "
        "(a) garantir la conformité du SMQ à la norme ISO, (b) garantir que les "
        "processus délivrent les résultats attendus, (c) rendre compte des "
        "performances du SMQ à la direction, (d) promouvoir l'orientation client, "
        "(e) garantir l'intégrité du SMQ lors des modifications.'\n\n"
        "Le manuel EQMS indique : 'Les membres de la direction sont en dernier "
        "ressort responsables de la qualité des produits et services.' et "
        "'Le Responsable EQMS est chargé de s'assurer que les risques sont "
        "éliminés ou réduits au niveau ALARP.'\n\n"
        "Les cinq responsabilités de la clause 5.3 sont-elles explicitement "
        "attribuées ?"
    ),
    expected_any=["5.3"],
    top_k_pass=10,
    difficulty="expert",
    fmt="verb_detection",
),

# ── 40 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="40. 8.2.1(e) Communication avec les clients – actions de contingence",
    query=(
        "La clause 8.2.1(e) de l'ISO 9001 exige d'établir des exigences "
        "spécifiques pour les actions de contingence, le cas échéant. L'EQMS "
        "Spotless liste les formats de communication client : brochures, demandes, "
        "commandes, bons de livraison, e-mails et réclamations. Aborde-t-il "
        "les actions de contingence ?"
    ),
    expected_any=["8.2.1"],
    top_k_pass=10,
    difficulty="expert",
    fmt="gap_analysis",
),

# ── 41 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="41. 10.3 Amélioration continue – au-delà de l'action corrective",
    query=(
        "La clause 10.3 de l'ISO 9001 exige que l'organisme prenne en compte "
        "les résultats d'analyse/évaluation ET les résultats de la revue de "
        "direction pour déterminer s'il existe des besoins ou opportunités "
        "d'amélioration continue.\n\n"
        "La section 10.3 de l'EQMS indique : 'Spotless améliore continuellement "
        "l'efficacité de son système de management de la qualité par l'application "
        "efficace des politiques d'entreprise, des objectifs, de l'audit, de "
        "l'analyse des données, des actions correctives et préventives, et des "
        "revues de direction.'\n\n"
        "Remarque : l'ISO 9001:2015 a supprimé l''action préventive' en tant que "
        "concept distinct. Évaluez cet anachronisme."
    ),
    expected_any=["10.3"],
    top_k_pass=10,
    difficulty="expert",
    fmt="clause_question",
),

# ── 42 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="42. Rapport d'écarts consolidé – clause 8 opérationnelle complète",
    query=(
        "Produisez un rapport d'écarts consolidé pour l'ensemble de la clause 8 "
        "de l'ISO 9001 (Réalisation des activités opérationnelles) : 8.1, "
        "8.2.1 à 8.2.4, 8.3.1 à 8.3.6, 8.4.1 à 8.4.3, 8.5.1 à 8.5.6, 8.6, 8.7. "
        "Pour chaque sous-clause, indiquez : Couvert / Partiel / Absent."
    ),
    expected_any=["8.1", "8.2.1", "8.2.2", "8.2.3", "8.2.4",
                  "8.3.1", "8.3.2", "8.3.3", "8.3.4", "8.3.5", "8.3.6",
                  "8.4.1", "8.4.2", "8.4.3",
                  "8.5.1", "8.5.2", "8.5.3", "8.5.4", "8.5.5", "8.5.6",
                  "8.6", "8.7"],
    top_k_pass=10,
    difficulty="expert",
    fmt="multi_clause_matrix",
),

# ── 43 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="43. 8.5.3 Correction actionnable – ajout d'une section propriété client",
    query=(
        "Générez une correction actionnable pour la section 8.5.3 manquante. "
        "Incluez : (1) le texte de section proposé, (2) l'emplacement d'insertion "
        "dans le manuel, (3) les sections existantes devant le référencer, "
        "(4) les enregistrements à créer."
    ),
    expected_any=["8.5.3"],
    top_k_pass=10,
    difficulty="expert",
    fmt="recommendation_request",
),

# ── 44 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="44. 7.4 Chaîne de traçabilité – constat → clause → extrait du document",
    query=(
        "Pour le constat 'Le manuel EQMS ne définit pas qui communique en interne "
        "sur les modifications de la politique qualité', produisez une chaîne de "
        "traçabilité complète :\n"
        "1. Clause ISO et sous-exigence\n"
        "2. Texte exact du manuel EQMS examiné\n"
        "3. Ce qui est présent vs ce qui manque\n"
        "4. Justification du statut de l'écart"
    ),
    expected_any=["7.4"],
    top_k_pass=10,
    difficulty="expert",
    fmt="evidence_trace",
),

# ── 45 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="45. 7.1.6 Connaissances organisationnelles – sources et gestion",
    query=(
        "7.1.6 Connaissances organisationnelles\n"
        "Spotless reconnaît que les connaissances organisationnelles constituent "
        "une ressource précieuse. Pour garantir leur conservation et leur "
        "transmission, elles sont consignées dans des informations documentées "
        "et intégrées dans nos processus et services.\n"
        "Les sources internes comprennent : processus documentés, spécifications "
        "antérieures, expérience des personnes qualifiées, technologies et "
        "infrastructures.\n"
        "Les sources externes comprennent : d'autres normes ISO, articles de "
        "recherche, webinaires, connaissances des clients et parties prenantes."
    ),
    expected_any=["7.1.6"],
    top_k_pass=10,
    difficulty="expert",
    fmt="section_extract",
),

# ── 46 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="46. 8.1 / 7.5.2 Procédure non datée, sans responsable (NC)",
    query=(
        "Procédure : Nettoyage des locaux sensibles\n\n"
        "Le nettoyage des locaux sensibles (salles blanches, laboratoires) "
        "doit être effectué selon un protocole strict. Les produits utilisés "
        "doivent être conformes aux spécifications. Un contrôle visuel est "
        "réalisé après chaque intervention.\n\n"
        "Évaluer ce document par rapport aux exigences de maîtrise "
        "opérationnelle (ISO 9001 clause 8.1) et d'information documentée "
        "(clause 7.5.2)."
    ),
    expected_any=["8.1", "7.5.2"],
    top_k_pass=10,
    difficulty="expert",
    fmt="paragraph_non_conformity",
),

# ── 47 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="47. Cas limite : 8.7 situations d'urgence – absent de l'ISO 9001",
    query=(
        "L'EQMS Spotless inclut une section '8.7 Maîtrise des situations "
        "d'urgence' faisant référence à la Politique HSE, aux Procédures "
        "incendie et au Plan de continuité d'activité. La préparation aux "
        "situations d'urgence est une exigence ISO 14001 (8.2) et non une "
        "clause de l'ISO 9001:2015. Comment l'agent doit-il traiter ce cas ?"
    ),
    expected_any=["8.1"],
    top_k_pass=10,
    difficulty="expert",
    fmt="clause_question",
),

# ── 48 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="48. Matrice de couverture normative – analyse complète du document",
    query=(
        "Produisez la 'Matrice de Couverture Normative' complète telle que "
        "spécifiée dans le cahier des charges de l'Agent 2 (Sortie §3.1) : "
        "clauses ISO 9001 en lignes, sections du manuel EQMS en colonnes. "
        "Indiquez pour chaque intersection : Couvert / Partiel / Absent / N/A."
    ),
    expected_any=["4.1", "4.2", "4.3", "4.4",
                  "5.1", "5.2", "5.3",
                  "6.1", "6.2", "6.3",
                  "7.1", "7.2", "7.3", "7.4", "7.5",
                  "8.1", "8.2", "8.3", "8.4", "8.5", "8.6", "8.7",
                  "9.1", "9.2", "9.3",
                  "10.1", "10.2", "10.3"],
    top_k_pass=10,
    difficulty="expert",
    fmt="multi_clause_matrix",
),

# ── 49 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="49. 5.1 Génération d'une check-list d'audit – section 5 Leadership",
    query=(
        "Générez une check-list d'audit pour vérifier l'application de la "
        "section 5 de l'EQMS (Leadership et Gouvernance) telle que spécifiée "
        "dans la Sortie §3.3 de l'Agent 2. Format : questions d'audit, "
        "références dans le document, références normatives (clauses ISO 9001) "
        "et obligations internes."
    ),
    expected_any=["5.1.1", "5.1.2", "5.2", "5.3"],
    top_k_pass=10,
    difficulty="expert",
    fmt="recommendation_request",
),

# ── 50 ───────────────────────────────────────────────────────────────────────
TestCase(
    name="50. Résumé exécutif – évaluation globale de la conformité",
    query=(
        "Produisez un résumé exécutif pour l'évaluation de la conformité du "
        "manuel EQMS Spotless par rapport à l'ISO 9001:2015, tel que spécifié "
        "dans la Sortie §3.3 de l'Agent 2. Inclure : score global de conformité, "
        "écarts critiques, points forts et 5 actions prioritaires."
    ),
    expected_any=["4.1", "5.1", "6.1", "7.5", "8.5", "9.2", "10.2"],
    top_k_pass=10,
    difficulty="expert",
    fmt="evidence_trace",
),

]


# ── Inline embedder ───────────────────────────────────────────────────────────

class _OllamaEmbedder:
    def __init__(self, base_url: str, model: str) -> None:
        self._endpoint = f"{base_url}/api/embeddings"
        self._model = model

    async def embed_text(self, text: str) -> list:
        resp = await asyncio.to_thread(
            requests.post,
            self._endpoint,
            json={"model": self._model, "prompt": text},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()["embedding"]


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class PathResult:
    passed: bool
    top3: List[str]
    matched_at: Optional[int]
    error: Optional[str]


@dataclass
class CompareResult:
    tc: TestCase
    tq: Optional[TransformedQuery]
    transform_error: Optional[str]
    dense: PathResult
    hybrid: PathResult


# ── Helpers ───────────────────────────────────────────────────────────────────

DIFF_ICON = {"easy": "○", "medium": "◑", "hard": "●", "expert": "★"}

def _sep(char: str = "─", width: int = 84) -> None:
    print(char * width)

def _truncate(s: str, n: int = 70) -> str:
    return s if len(s) <= n else s[:n - 1] + "…"

def _eval_path(chunks: List[RetrievedChunk], tc: TestCase) -> PathResult:
    top3 = [c.clause_number for c in chunks[:3]]
    matched_at = None
    for i, chunk in enumerate(chunks[:RECALL_K], start=1):
        if any(chunk.clause_number.startswith(pfx) for pfx in tc.expected_any):
            matched_at = i
            break
    return PathResult(passed=matched_at is not None, top3=top3,
                      matched_at=matched_at, error=None)

def _error_path(msg: str) -> PathResult:
    return PathResult(passed=False, top3=[], matched_at=None, error=msg)


# ── Runner ────────────────────────────────────────────────────────────────────

async def run_tests(
    dense_retriever: DenseRetriever,
    hybrid_retriever: HybridRetriever,
) -> List[CompareResult]:
    results: List[CompareResult] = []
    for tc in TESTS:
        tq: Optional[TransformedQuery] = None
        transform_error: Optional[str] = None
        try:
            tq = transform(tc.query, norm_filter=NORM_FILTER, language=LANGUAGE)
        except Exception as exc:
            transform_error = f"{type(exc).__name__}: {exc}"
            results.append(CompareResult(tc=tc, tq=None,
                transform_error=transform_error,
                dense=_error_path("transform failed"),
                hybrid=_error_path("transform failed")))
            continue

        try:
            dense_chunks = await dense_retriever.retrieve(tq, top_k=RETRIEVE_K)
            dense_result = _eval_path(dense_chunks, tc)
        except DenseEmptyCorpusError as exc:
            dense_result = _error_path(f"EmptyCorpusError: {exc}")
        except Exception as exc:
            dense_result = _error_path(f"{type(exc).__name__}: {exc}")

        try:
            hybrid_chunks = await hybrid_retriever.retrieve(tq, top_k=RETRIEVE_K)
            hybrid_result = _eval_path(hybrid_chunks, tc)
        except HybridEmptyCorpusError as exc:
            hybrid_result = _error_path(f"EmptyCorpusError: {exc}")
        except Exception as exc:
            hybrid_result = _error_path(f"{type(exc).__name__}: {exc}")

        results.append(CompareResult(tc=tc, tq=tq, transform_error=None,
                                     dense=dense_result, hybrid=hybrid_result))
    return results


# ── Print per-result detail ───────────────────────────────────────────────────

def _pass_icon(r: PathResult) -> str:
    return "✓" if r.passed else "✗"

def _rank_str(r: PathResult) -> str:
    if r.error:
        return f"ERROR: {r.error}"
    rank = f"rank {r.matched_at}" if r.matched_at else f"PAS DE CORRESPONDANCE dans top-{RECALL_K}"
    return f"top-3: {r.top3}  │  {rank}"

def print_detail(r: CompareResult) -> None:
    overall_icon = "✓" if (r.dense.passed or r.hybrid.passed) else "✗"
    diff_icon = DIFF_ICON.get(r.tc.difficulty, " ")
    print(f"\n  {overall_icon} {diff_icon} {r.tc.name}")
    print(f"     fmt={r.tc.fmt:<28} difficulté={r.tc.difficulty}  seuil=top-{RECALL_K} (mode recall)")
    print(f"     attendu ∈ {r.tc.expected_any}")
    query_preview = _truncate(r.tc.query.replace("\n", " "))
    print(f"     requête : \"{query_preview}\"")

    if r.transform_error:
        print(f"     ERREUR DE TRANSFORMATION : {r.transform_error}")
        return

    assert r.tq is not None
    hyde_str = "OUI" if r.tq.hyde_used else "non"
    vocab_preview = r.tq.iso_vocab_hits[:5] if r.tq.iso_vocab_hits else []
    print(f"     HyDE={hyde_str}  iso_vocab_hits={vocab_preview}")
    print(f"     bm25_tokens ({len(r.tq.bm25_tokens)}) : {sorted(r.tq.bm25_tokens)}")

    print(f"     Dense seul  {_pass_icon(r.dense)}  │  {_rank_str(r.dense)}")
    print(f"     Hybride     {_pass_icon(r.hybrid)}  │  {_rank_str(r.hybrid)}")

    if not r.dense.error and not r.hybrid.error:
        if r.dense.top3 == r.hybrid.top3:
            print(f"     Diff classement : NON  (top-3 identiques)")
        else:
            changed = [i + 1 for i, (d, h) in enumerate(zip(r.dense.top3, r.hybrid.top3)) if d != h]
            print(f"     Diff classement : OUI  (positions {changed} modifiées)")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> int:
    print()
    _sep("═", 84)
    print(" Comparaison Pipeline Complet — Dense seul vs Hybride")
    print(f" Corpus   : ISO 9001 · langue={LANGUAGE} · Qdrant {QDRANT_HOST}:{QDRANT_PORT}")
    print(f" Embedder : {OLLAMA_MODEL} via {OLLAMA_URL}")
    n_easy   = sum(1 for t in TESTS if t.difficulty == "easy")
    n_medium = sum(1 for t in TESTS if t.difficulty == "medium")
    n_hard   = sum(1 for t in TESTS if t.difficulty == "hard")
    n_expert = sum(1 for t in TESTS if t.difficulty == "expert")
    print(f" Tests    : {len(TESTS)}  (facile={n_easy}  moyen={n_medium}  difficile={n_hard}  expert={n_expert})")
    print(f" Légende  : ○ facile  ◑ moyen  ● difficile  ★ expert")
    _sep("═", 84)

    embedder         = _OllamaEmbedder(OLLAMA_URL, OLLAMA_MODEL)
    qdrant           = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    dense_retriever  = DenseRetriever(embedder=embedder, qdrant=qdrant)
    hybrid_retriever = HybridRetriever(embedder=embedder, qdrant=qdrant)

    print("\nLancement des tests (transform + dense + hybride par cas) …")
    results = await run_tests(dense_retriever, hybrid_retriever)

    _sep()
    for r in results:
        print_detail(r)

    dense_passed  = [r for r in results if r.dense.passed]
    hybrid_passed = [r for r in results if r.hybrid.passed]
    ranking_diffs = sum(
        1 for r in results
        if not r.dense.error and not r.hybrid.error and r.dense.top3 != r.hybrid.top3
    )

    print()
    _sep("═", 84)
    print(f"\n RÉSULTATS")
    print(f"   Dense seul : {len(dense_passed)}/{len(results)} passés")
    print(f"   Hybride    : {len(hybrid_passed)}/{len(results)} passés")
    print(f"   Classement modifié dans {ranking_diffs}/{len(results)} cas "
          f"(signal sparse actif)")
    print()

    by_diff: dict = {"easy": [], "medium": [], "hard": [], "expert": []}
    for r in results:
        by_diff[r.tc.difficulty].append((r.dense.passed, r.hybrid.passed))

    labels_fr = {"easy": "facile", "medium": "moyen", "hard": "difficile", "expert": "expert"}
    print(" Score par niveau de difficulté :")
    print(f"   {'':10}  {'Dense':>6}  {'Hybride':>7}  barre (Dense░ / Hybride█)")
    for d, pairs in by_diff.items():
        n = len(pairs)
        if n == 0:
            continue
        nd = sum(p[0] for p in pairs)
        nh = sum(p[1] for p in pairs)
        bar_d = "░" * nd + " " * (n - nd)
        bar_h = "█" * nh + " " * (n - nh)
        icon = DIFF_ICON[d]
        print(f"   {icon} {labels_fr[d]:<10}  {nd}/{n}      {nh}/{n}      [{bar_d}] [{bar_h}]")

    print()
    failed_dense  = [r for r in results if not r.dense.passed]
    failed_hybrid = [r for r in results if not r.hybrid.passed]
    if failed_dense or failed_hybrid:
        print(" Cas échoués :")
        for r in results:
            d_fail = not r.dense.passed
            h_fail = not r.hybrid.passed
            if d_fail or h_fail:
                label = []
                if d_fail:  label.append("dense")
                if h_fail:  label.append("hybride")
                diff_icon = DIFF_ICON.get(r.tc.difficulty, " ")
                print(f"   ✗ {diff_icon} {r.tc.name}  [{', '.join(label)} échoué]")
        print()

    dense_pct  = len(dense_passed)  / len(results) * 100
    hybrid_pct = len(hybrid_passed) / len(results) * 100

    for label, pct in [("Dense seul ", dense_pct), ("Hybride    ", hybrid_pct)]:
        if pct == 100:
            print(f" 🟢 {label}: Tous les tests passés ({pct:.0f}%)")
        elif pct >= 80:
            print(f" 🟡 {label}: La plupart des tests passés ({pct:.0f}%)")
        else:
            print(f" 🔴 {label}: Trop d'échecs ({pct:.0f}%) — investiguer le pipeline")

    print()
    _sep("═", 84)
    print()
    return 0 if (len(dense_passed) == len(results) and len(hybrid_passed) == len(results)) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))