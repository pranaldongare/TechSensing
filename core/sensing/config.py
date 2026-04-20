"""
Configuration for the Tech Sensing module.
Curated RSS feeds, default search queries, pipeline parameters,
and domain-specific presets for topic categories, industry segments,
and key people watchlists.
"""

from dataclasses import dataclass, field
from typing import List

DEFAULT_DOMAIN = "Generative AI"
LOOKBACK_DAYS = 7
MAX_ARTICLES_PER_FEED = 20
MAX_SEARCH_RESULTS = 30
ARTICLE_BATCH_SIZE = 6  # Articles per LLM classification call
MIN_RELEVANCE_SCORE = 0.3
DEDUP_SIMILARITY_THRESHOLD = 0.85

# ── General technology / broad tech RSS feeds ──
# These are domain-agnostic and always included.
GENERAL_RSS_FEEDS = [
    "https://www.technologyreview.com/feed/",
    "https://techcrunch.com/feed/",
    "https://venturebeat.com/feed/",
    "https://www.wired.com/feed/rss",
    "https://arstechnica.com/feed/",
]

# ── Domain-specific RSS feed presets ──
# Keyed by lowercase domain keywords. Matched if any keyword appears in the user domain.
DOMAIN_RSS_FEEDS = {
    "ai": [
        "http://arxiv.org/rss/cs.AI",
        "http://arxiv.org/rss/cs.CL",
        "http://arxiv.org/rss/cs.LG",
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://venturebeat.com/category/ai/feed/",
        "https://the-decoder.com/feed/",
        "https://www.marktechpost.com/feed/",
        "https://hnrss.org/newest?q=LLM+OR+GPT+OR+AI+OR+generative",
        "https://www.reddit.com/r/MachineLearning/.rss",
        "https://blog.google/technology/ai/rss/",
        "https://openai.com/blog/rss.xml",
    ],
    "robotics": [
        "http://arxiv.org/rss/cs.RO",
        "https://www.therobotreport.com/feed/",
        "https://spectrum.ieee.org/feeds/topic/robotics.rss",
        "https://www.reddit.com/r/robotics/.rss",
    ],
    "quantum": [
        "http://arxiv.org/rss/quant-ph",
        "https://www.reddit.com/r/QuantumComputing/.rss",
        "https://quantumcomputingreport.com/feed/",
    ],
    "cybersecurity": [
        "https://www.darkreading.com/rss.xml",
        "https://feeds.feedburner.com/TheHackersNews",
        "https://krebsonsecurity.com/feed/",
        "https://www.bleepingcomputer.com/feed/",
        "https://www.reddit.com/r/netsec/.rss",
    ],
    "blockchain": [
        "https://cointelegraph.com/rss",
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://www.reddit.com/r/CryptoCurrency/.rss",
    ],
    "cloud": [
        "https://aws.amazon.com/blogs/aws/feed/",
        "https://cloud.google.com/blog/rss",
        "https://azure.microsoft.com/en-us/blog/feed/",
        "https://www.reddit.com/r/cloudcomputing/.rss",
    ],
}


def get_feeds_for_domain(domain: str) -> List[str]:
    """
    Return RSS feeds relevant to the user's domain.
    Always includes general tech feeds + domain-specific feeds if matched.
    """
    feeds = list(GENERAL_RSS_FEEDS)
    domain_lower = domain.lower()

    for keyword, domain_feeds in DOMAIN_RSS_FEEDS.items():
        if keyword in domain_lower:
            feeds.extend(domain_feeds)

    # If no domain-specific match, add AI feeds as fallback only if
    # domain contains generic tech terms
    if len(feeds) == len(GENERAL_RSS_FEEDS):
        # Add HackerNews broad search for the domain
        safe_domain = domain.replace(" ", "+")
        feeds.append(f"https://hnrss.org/newest?q={safe_domain}")

    return feeds


def get_search_queries_for_domain(
    domain: str,
    must_include: List[str] | None = None,
) -> List[str]:
    """
    Generate DuckDuckGo search queries tailored to the user's domain.
    """
    queries = [
        f"{domain} latest developments this week",
        f"{domain} breakthrough news this week",
        f"{domain} new technology announcements",
        f"{domain} industry trends this week",
        f"{domain} open source news this week",
    ]

    # Add must-include keyword queries
    if must_include:
        for kw in must_include[:5]:  # Cap at 5 extra queries
            queries.append(f"{domain} {kw} news this week")

    return queries


def get_patent_queries_for_domain(
    domain: str,
    must_include: List[str] | None = None,
) -> List[str]:
    """
    Generate patent-specific keyword lists for the USPTO PatentsView API.
    Returns keywords (not full queries) suitable for text matching.
    """
    domain_lower = domain.lower()

    # Domain-specific patent keyword mappings
    patent_keywords: dict[str, List[str]] = {
        "ai": [
            "machine learning", "neural network", "deep learning",
            "natural language processing", "large language model",
            "generative artificial intelligence", "transformer model",
        ],
        "robotics": [
            "autonomous robot", "robotic manipulation", "robot control",
            "humanoid robot", "robotic arm", "mobile robot",
        ],
        "quantum": [
            "quantum computing", "quantum circuit", "qubit",
            "quantum error correction", "quantum processor",
        ],
        "cybersecurity": [
            "intrusion detection", "encryption method", "authentication system",
            "malware detection", "network security",
        ],
        "blockchain": [
            "distributed ledger", "smart contract", "consensus mechanism",
            "blockchain protocol", "decentralized application",
        ],
        "cloud": [
            "cloud computing", "serverless computing", "container orchestration",
            "distributed computing system", "edge computing",
        ],
    }

    keywords = [domain]  # Always include the domain itself
    for key, kws in patent_keywords.items():
        if key in domain_lower:
            keywords.extend(kws)
            break

    # If no domain-specific match, add generic tech keywords
    if len(keywords) == 1:
        keywords.extend([
            f"{domain} system", f"{domain} method", f"{domain} apparatus",
        ])

    # Append must_include keywords
    if must_include:
        keywords.extend(must_include[:3])

    return keywords


# ── Domain-specific presets for prompts ──
# Each preset provides topic categories, industry segments, and an optional
# key-people watchlist so that prompts are tailored to the target domain
# instead of using hardcoded GenAI-centric content.


@dataclass
class DomainPreset:
    """Prompt content blocks for a specific domain."""

    topic_categories: str
    industry_segments: str
    key_people: List[str] = field(default_factory=list)


_GENERIC_PRESET = DomainPreset(
    topic_categories=(
        "TOPIC CATEGORY DEFINITIONS:\n"
        "- Core Technology: Fundamental research, breakthroughs, new algorithms, protocols, or architectures\n"
        "- Infrastructure & Platforms: Hardware, compute, cloud services, tooling, and developer platforms\n"
        "- Research & Standards: Academic papers, benchmarks, standards bodies, open-source releases\n"
        "- Commercial & Enterprise: Product launches, enterprise adoption, case studies, market moves\n"
        "- Ecosystem & Community: Partnerships, funding, M&A, community events, regulatory developments\n"
    ),
    industry_segments=(
        "INDUSTRY SEGMENTS (use these for headline_moves and market_signals):\n"
        "- Technology Leaders: Established companies leading innovation in this domain\n"
        "- Infrastructure Providers: Hardware, cloud, and platform providers enabling the ecosystem\n"
        "- Startups & Challengers: Emerging companies and disruptors\n"
        "- Research & Academia: Universities, research labs, standards bodies\n"
        "- Investors & Ecosystem: VCs, accelerators, public intellectuals, community builders\n"
    ),
)

DOMAIN_PRESETS = {
    "ai": DomainPreset(
        topic_categories=(
            "TOPIC CATEGORY DEFINITIONS:\n"
            "- Foundation Models & Agents: Foundation model releases, agents, major product launches, benchmarks\n"
            "- Safety & Governance: AI safety, alignment, regulation, governance, ethics, responsible AI\n"
            "- Infrastructure & Compute: GPUs, TPUs, data centers, compute infrastructure, large investments\n"
            "- Open Source & Research: Open-source releases, research papers, benchmark results, datasets\n"
            "- Partnerships & Strategy: M&A, partnerships, strategic shifts, funding rounds, market moves\n"
        ),
        industry_segments=(
            "INDUSTRY SEGMENTS (use these for headline_moves and market_signals):\n"
            "- Frontier Labs: Frontier AI labs and their leaders (e.g., OpenAI, Anthropic, Google DeepMind, xAI)\n"
            "- Big Tech Platforms: Major tech platforms integrating AI (e.g., Microsoft, Google/Alphabet, Meta, Apple, Amazon)\n"
            "- Infra & Chips: Hardware, compute, and infrastructure providers (e.g., NVIDIA, Qualcomm, AMD, cloud providers)\n"
            "- Ethics & Policy: AI safety researchers, regulators, policy makers, governance bodies\n"
            "- Ecosystem & Investors: Independent founders, VCs, startups, ecosystem builders, public intellectuals\n"
        ),
        key_people=[
            "Sam Altman", "Demis Hassabis", "Dario Amodei", "Jensen Huang",
            "Satya Nadella", "Sundar Pichai", "Mark Zuckerberg", "Yann LeCun",
        ],
    ),
    "blockchain": DomainPreset(
        topic_categories=(
            "TOPIC CATEGORY DEFINITIONS:\n"
            "- DeFi & Smart Contracts: Decentralized finance protocols, DEXs, lending, yield, smart contract platforms\n"
            "- Infrastructure & L1/L2: Layer-1 chains, Layer-2 scaling, bridges, consensus mechanisms, node infrastructure\n"
            "- Security & Regulation: Audits, exploits, regulatory actions, compliance frameworks, legal developments\n"
            "- NFTs & Digital Assets: NFTs, tokenization, real-world assets (RWA), digital identity, gaming\n"
            "- Ecosystem & Adoption: Enterprise adoption, partnerships, funding rounds, DAO governance, community events\n"
        ),
        industry_segments=(
            "INDUSTRY SEGMENTS (use these for headline_moves and market_signals):\n"
            "- L1 Protocols: Layer-1 blockchain platforms (e.g., Ethereum, Solana, Bitcoin, Cardano, Avalanche)\n"
            "- L2 & Scaling: Layer-2 scaling and interoperability (e.g., Arbitrum, Optimism, Polygon, zkSync)\n"
            "- Exchanges & CeFi: Centralized exchanges and financial services (e.g., Binance, Coinbase, Kraken)\n"
            "- DeFi Protocols: Decentralized finance platforms (e.g., Uniswap, Aave, MakerDAO, Lido)\n"
            "- Investors & Ecosystem: VCs, accelerators, DAOs, foundations, public intellectuals\n"
        ),
        key_people=[
            "Vitalik Buterin", "Changpeng Zhao", "Brian Armstrong",
            "Anatoly Yakovenko", "Charles Hoskinson",
        ],
    ),
    "quantum": DomainPreset(
        topic_categories=(
            "TOPIC CATEGORY DEFINITIONS:\n"
            "- Quantum Hardware: Qubit technologies, processors, cryogenics, error correction, quantum networking\n"
            "- Quantum Algorithms & Software: Algorithms, compilers, simulators, SDKs, programming frameworks\n"
            "- Quantum Applications: Optimization, drug discovery, materials science, cryptography, finance\n"
            "- Post-Quantum Cryptography: PQC standards, migration strategies, quantum-safe protocols\n"
            "- Ecosystem & Funding: Partnerships, government programs, VC funding, talent, education\n"
        ),
        industry_segments=(
            "INDUSTRY SEGMENTS (use these for headline_moves and market_signals):\n"
            "- Hardware Providers: Quantum computer manufacturers (e.g., IBM Quantum, Google Quantum AI, IonQ, Rigetti)\n"
            "- Software & Cloud: Quantum software platforms and cloud access (e.g., Amazon Braket, Azure Quantum, Qiskit, Cirq)\n"
            "- Research Labs: Government and academic research (e.g., NIST, national labs, university programs)\n"
            "- Enterprise Adopters: Companies exploring quantum advantage (e.g., JPMorgan, BMW, Roche)\n"
            "- Startups & Investors: Quantum startups and VCs (e.g., PsiQuantum, Xanadu, QuEra)\n"
        ),
        key_people=[
            "Jay Gambetta", "Hartmut Neven", "Peter Chapman",
            "Chad Rigetti", "Jeremy O'Brien",
        ],
    ),
    "cybersecurity": DomainPreset(
        topic_categories=(
            "TOPIC CATEGORY DEFINITIONS:\n"
            "- Threat Intelligence: New vulnerabilities, CVEs, APT campaigns, malware, ransomware\n"
            "- Zero Trust & IAM: Identity management, zero-trust architecture, authentication, access control\n"
            "- Cloud & Application Security: Cloud security posture, DevSecOps, API security, container security\n"
            "- Compliance & Regulation: Data privacy laws, frameworks (NIST, ISO 27001), audit requirements\n"
            "- Tools & Platforms: SIEM, SOAR, EDR, XDR, security tooling, open-source security projects\n"
        ),
        industry_segments=(
            "INDUSTRY SEGMENTS (use these for headline_moves and market_signals):\n"
            "- Security Vendors: Major cybersecurity companies (e.g., CrowdStrike, Palo Alto Networks, Fortinet, Zscaler)\n"
            "- Big Tech Security: Security divisions of major platforms (e.g., Microsoft Security, Google Mandiant, AWS Security)\n"
            "- Government & Defense: Government agencies, defense contractors, CISA, NSA, ENISA\n"
            "- Research & Advisories: Threat researchers, CERTs, vulnerability databases, security conferences\n"
            "- Startups & Investors: Emerging security companies, VC activity, acquisitions\n"
        ),
        key_people=[
            "George Kurtz", "Nikesh Arora", "Kevin Mandia",
            "Jen Easterly", "Mikko Hyppönen",
        ],
    ),
    "cloud": DomainPreset(
        topic_categories=(
            "TOPIC CATEGORY DEFINITIONS:\n"
            "- Cloud Infrastructure: IaaS, compute, storage, networking, data centers, availability zones\n"
            "- Serverless & Edge: Serverless computing, edge compute, CDN, IoT edge platforms\n"
            "- DevOps & Platform Engineering: CI/CD, IaC, Kubernetes, containers, observability, platform engineering\n"
            "- Data & Analytics: Cloud databases, data lakes, streaming, analytics, data mesh\n"
            "- Multi-Cloud & Strategy: Hybrid cloud, multi-cloud, cost optimization, migration, FinOps\n"
        ),
        industry_segments=(
            "INDUSTRY SEGMENTS (use these for headline_moves and market_signals):\n"
            "- Hyperscalers: Major cloud providers (e.g., AWS, Microsoft Azure, Google Cloud, Oracle Cloud)\n"
            "- Platform Vendors: Cloud-native platforms and tools (e.g., HashiCorp, Datadog, Snowflake, Confluent)\n"
            "- Enterprise Adopters: Large enterprises driving cloud transformation\n"
            "- Open Source & CNCF: Cloud-native open-source projects and the CNCF ecosystem\n"
            "- Startups & Challengers: Emerging cloud-native startups and disruptors\n"
        ),
        key_people=[
            "Matt Garman", "Satya Nadella", "Thomas Kurian",
            "Safra Catz", "Solomon Hykes",
        ],
    ),
    "robotics": DomainPreset(
        topic_categories=(
            "TOPIC CATEGORY DEFINITIONS:\n"
            "- Autonomous Systems: Self-driving vehicles, drones, autonomous mobile robots, navigation\n"
            "- Industrial Automation: Manufacturing robots, cobots, warehouse automation, logistics\n"
            "- AI & Perception: Computer vision, sensor fusion, reinforcement learning for robotics, sim-to-real\n"
            "- Hardware & Actuators: Robotic hardware, actuators, grippers, sensors, humanoid platforms\n"
            "- Applications & Deployment: Healthcare robots, service robots, agriculture, defense, consumer\n"
        ),
        industry_segments=(
            "INDUSTRY SEGMENTS (use these for headline_moves and market_signals):\n"
            "- Robot Manufacturers: Major robotics companies (e.g., Boston Dynamics, ABB, FANUC, Universal Robots)\n"
            "- Autonomous Vehicles: Self-driving companies (e.g., Waymo, Tesla, Cruise, Aurora)\n"
            "- Big Tech Robotics: Tech giants investing in robotics (e.g., NVIDIA Isaac, Google DeepMind, Amazon Robotics)\n"
            "- Research & Academia: University labs, DARPA, ROS community, IEEE RAS\n"
            "- Startups & Investors: Emerging robotics startups, VC activity, accelerators\n"
        ),
        key_people=[
            "Marc Raibert", "Elon Musk", "Jim Fan",
            "Pieter Abbeel", "Daniela Rus",
        ],
    ),
}


def get_preset_for_domain(domain: str) -> DomainPreset:
    """
    Return the prompt preset (topic categories, industry segments, key people)
    for the given domain.  Uses keyword matching, falling back to a generic
    preset for unknown domains.
    """
    domain_lower = domain.lower()
    for keyword, preset in DOMAIN_PRESETS.items():
        if keyword in domain_lower:
            return preset
    return _GENERIC_PRESET


# ── Model Releases: Structured Source Configuration ──

# HuggingFace Hub API — significance thresholds to filter out noise
HF_MIN_DOWNLOADS = 1000
HF_MIN_LIKES = 50
HF_KNOWN_ORGS = [
    "meta-llama", "google", "microsoft", "mistralai", "Qwen",
    "deepseek-ai", "stabilityai", "alibaba-nlp", "THUDM",
    "01-ai", "tiiuae", "nvidia", "apple", "CohereForAI",
    "HuggingFaceH4", "bigscience", "EleutherAI", "allenai",
    "mosaicml", "databricks", "xai-org", "anthropics",
    "black-forest-labs", "ByteDance", "internlm", "Open-Orca",
    "NousResearch", "teknium", "lmsys", "BAAI",
]

# Major AI lab blogs — for proprietary/API-only model announcements
MAJOR_LAB_BLOG_FEEDS = {
    "OpenAI": "https://openai.com/blog/rss.xml",
    "Anthropic": "https://www.anthropic.com/rss.xml",
    "Google AI": "https://blog.google/technology/ai/rss/",
    "DeepMind": "https://deepmind.google/blog/rss.xml",
    "Cohere": "https://cohere.com/blog/rss.xml",
    "Mistral": "https://mistral.ai/feed.xml",
}

# Keywords in blog titles that indicate a model announcement
MODEL_ANNOUNCEMENT_KEYWORDS = [
    "introducing", "announcing", "launch", "release", "new model",
    "now available", "open source", "open weight", "meet ",
    "presenting", "unveiling",
]

# Targeted search queries for proprietary/API-only models (Tier 2b)
# These labs don't publish weights on HuggingFace, so we need DDG to find them.
PROPRIETARY_LAB_QUERIES = [
    "OpenAI new model release",
    "Anthropic Claude new model release",
    "Google Gemini new model release",
    "xAI Grok new model release",
    "Cohere new model release",
    "Mistral new model release",
]

# Artificial Analysis API (Tier 2c) — covers both open and proprietary models
# Free tier: 1000 req/day. Set ARTIFICIAL_ANALYSIS_API_KEY env var to enable.
ARTIFICIAL_ANALYSIS_API_URL = "https://artificialanalysis.ai/api/v2"
