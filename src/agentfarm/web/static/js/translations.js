/**
 * AgentFarm i18n - Swedish/English translations
 */

const TRANSLATIONS = {
    sv: {
        // Header
        "header.system": "SYSTEM",
        "header.online": "ONLINE",
        "header.agents": "AGENTER",
        "header.status": "STATUS",
        "header.guest": "GÄST",
        "header.synth": "SYNTH",

        // Section headers
        "section.neural_network": "NEURAL NETWORK",
        "section.data_stream": "DATASTRÖM",
        "section.command_interface": "KOMMANDOGRÄNSSNITT",
        "section.workflow_status": "WORKFLOW STATUS",
        "section.token_metrics": "TOKEN METRICS",
        "section.project_files": "PROJEKTFILER",
        "section.project_files_subtitle": "Filer som agenterna kan läsa",

        // Command input
        "input.placeholder": "Beskriv vad du vill skapa...\n\nT.ex: Skapa en Python-funktion som validerar e-postadresser med regex och returnerar True/False. Lägg till enhetstester.",
        "input.execute": "EXEKVERA",
        "input.hint": "Ju mer detaljer, desto bättre resultat · Ctrl+Enter för att köra",
        "input.multi_provider": "MULTI-PROVIDER MODE",

        // Workflow stages
        "stage.plan": "PLAN",
        "stage.ux": "UX",
        "stage.execute": "EXEKVERA",
        "stage.verify": "VERIFIERA",
        "stage.review": "GRANSKA",
        "stage.standby": "STANDBY",
        "stage.active": "AKTIV",
        "stage.complete": "KLAR",
        "stage.error": "FEL",
        "stage.skipped": "HOPPAD",

        // Launch button
        "launch.button": "STARTA PROJEKT",
        "launch.path": "Sökväg",

        // Token metrics
        "metrics.total_tokens": "TOTALA TOKENS",
        "metrics.avg_tps": "SNITT TOKENS/SEK",
        "metrics.latency": "LATENS (P95)",

        // File upload
        "files.info": "Ladda upp filer som agenterna ska ha tillgång till: kodfiler, dokumentation, specifikationer etc.",
        "files.drop_here": "SLÄPP FILER HÄR",
        "files.click_hint": "eller klicka för att välja filer",
        "files.formats": ".py .js .ts .json .md .txt .yaml .csv .pdf",
        "files.beta_required": "BETA OPERATOR KRÄVS",
        "files.become_beta": "BLI BETA OPERATOR",

        // Footer
        "footer.tagline": "NEURAL ORCHESTRATION SYSTEM",
        "footer.prompts": "DINA PROMPTER",
        "footer.beta_operator": "BETA OPERATOR",
        "footer.feedback": "FEEDBACK",
        "footer.hardware": "HÅRDVARA",

        // File browser modal
        "browser.title": "PROJEKT FILER",
        "browser.up": "UPP",
        "browser.download": "LADDA NER",

        // Beta Operator modal
        "beta.title": "BLI BETA OPERATOR",
        "beta.intro": "Lås upp alla premium-funktioner och hjälp till att forma AgentFarm!",
        "beta.price": "29 kr",
        "beta.price_period": "engångsbetalning",
        "beta.feature_workflows": "10 AI-drivna workflows",
        "beta.feature_files": "Filuppladdning (SecureVault)",
        "beta.feature_prompts": "Anpassade systemprompter",
        "beta.feature_feedback": "Direkt feedback till utvecklaren",
        "beta.feature_vpn": "VPN-access för säker anslutning",
        "beta.feature_zip": "ZIP-nedladdning av projekt",
        "beta.button": "BLI BETA OPERATOR",
        "beta.disclaimer": "Du får direkt tillgång. Betalning hanteras säkert via Stripe.",

        // Privacy section
        "beta.privacy_title": "INTEGRITET & DATASÄKERHET",
        "beta.privacy_intro": "Denna tjänst är byggd med \"Privacy by Design\" som grundprincip. Din data hanteras med högsta möjliga säkerhetsstandard.",
        "beta.privacy_airgap_title": "Total isolering (Air-gapped)",
        "beta.privacy_airgap_desc": "Till skillnad från molnbaserade AI-tjänster lämnar din data aldrig den lokala infrastrukturen. All bearbetning sker på dedikerad hårdvara (AMD Radeon 7800 XT) som är logiskt isolerad under tiden agenter arbetar med din kontext.",
        "beta.privacy_vpn_title": "Krypterad åtkomst",
        "beta.privacy_vpn_desc": "All kommunikation sker via en punkt-till-punkt-krypterad WireGuard VPN-tunnel. Ingen utomstående kan se eller avlyssna den data du delar.",
        "beta.privacy_gdpr_title": "GDPR-efterlevnad",
        "beta.privacy_gdpr_purpose": "Vi samlar endast in data som krävs för att utföra dina uppgifter",
        "beta.privacy_gdpr_training": "Din data används aldrig för att träna AI-modellerna",
        "beta.privacy_gdpr_delete": "När sessionen avslutas raderas din data från arbetsminne och lagring",
        "beta.privacy_nis2_title": "NIS2 & Cybersäkerhet",
        "beta.privacy_nis2_desc": "Genom att använda denna lokala lösning minskar du exponering mot tredjepartsrisker i molnet, vilket underlättar efterlevnad av NIS2-direktivet.",
        "beta.privacy_consent": "Genom att genomföra betalningen godkänner du att din data hanteras enligt ovanstående säkerhetsprotokoll.",

        // Tryout modal
        "tryout.title": "PROVA AGENTFARM",
        "tryout.intro": "Testa AI-agenter som skapar kod åt dig - helt gratis!",
        "tryout.feature_agents": "6 specialiserade AI-agenter",
        "tryout.feature_workflow": "1 gratis workflow",
        "tryout.button": "STARTA GRATIS",
        "tryout.disclaimer": "Ingen registrering. Gillar du det? Uppgradera till Beta Operator!",

        // Feedback modal
        "feedback.title": "SKICKA FEEDBACK",
        "feedback.category": "KATEGORI",
        "feedback.category_general": "Allmänt",
        "feedback.category_bug": "Bugg",
        "feedback.category_feature": "Ny funktion",
        "feedback.category_ux": "UX/Design",
        "feedback.category_performance": "Prestanda",
        "feedback.message": "MEDDELANDE",
        "feedback.message_placeholder": "Beskriv din feedback...",
        "feedback.email": "E-POST (valfritt)",
        "feedback.email_placeholder": "din@email.se",
        "feedback.rating": "BETYG (valfritt)",
        "feedback.submit": "SKICKA",

        // Datastream modal
        "datastream.title": "ALLA HÄNDELSER",
        "datastream.no_events": "Inga händelser ännu",
        "datastream.expand": "Expandera",

        // Context modal
        "context.title": "FÖRETAGSKONTEXT",
        "context.info": "Lägg till bakgrundinformation om ditt företag eller projekt. Agenterna kommer att ta hänsyn till detta i sina svar.",
        "context.placeholder": "T.ex: Vi är ett startup som bygger en app för...",
        "context.save": "SPARA",

        // Agent config modal
        "agents.title": "AGENT KONFIGURATION",
        "agents.info": "Anpassa varje agents beteende. Dina tillägg läggs till efter bas-prompten.",
        "agents.base_prompt": "BAS-PROMPT:",
        "agents.your_addition": "DITT TILLÄGG:",
        "agents.save_all": "SPARA ALLA",
        "agents.clear_all": "RENSA ALLA",

        // Agent names and descriptions
        "agent.orchestrator": "ORCHESTRATOR",
        "agent.orchestrator_desc": "Hjärnan i AgentFarm. Styr flödet mellan agenter, hanterar loop-detektering och kvalitetsspärr.",
        "agent.planner": "PLANNER",
        "agent.planner_desc": "Chefsarkitekt. Bryter ner problem till exekverbar roadmap med sekventiell JSON-plan.",
        "agent.ux_designer": "UX DESIGNER",
        "agent.ux_designer_desc": "Ansvarar för gränssnitt, API-kontrakt och användarflöden. Följer 80-tals Sci-Fi estetik som default.",
        "agent.executor": "EXECUTOR",
        "agent.executor_desc": "Seniordeveloper. Skriver ren, säker kod i isolerad sandbox. Följer kodstilar från kontext.",
        "agent.verifier": "VERIFIER",
        "agent.verifier_desc": "QA-ingenjör. Hittar buggar, kör tester i sandbox, godkänner endast om alla tester passerar.",
        "agent.reviewer": "REVIEWER",
        "agent.reviewer_desc": "Slutgiltig granskning. Verifierar att resultatet matchar krav och att ZIP-exporten är säker.",

        // Placeholders
        "placeholder.orchestrator": "T.ex: Prioritera snabbhet över precision...",
        "placeholder.planner": "T.ex: Använd alltid microservices-arkitektur...",
        "placeholder.ux_designer": "T.ex: Använd vårt designsystem med blå primärfärg...",
        "placeholder.executor": "T.ex: Använd TypeScript och skriv JSDoc-kommentarer...",
        "placeholder.verifier": "T.ex: Kräv 80% code coverage...",
        "placeholder.reviewer": "T.ex: Kontrollera att inga API-nycklar finns i koden...",

        // Hardware page
        "hw.back": "TILLBAKA TILL TERMINAL",
        "hw.title": "HARDWARE TERMINAL",
        "hw.subtitle": "BYGG DIN EGNA AI-DATOR - KÖR LLMs LOKALT",
        "hw.rocm_badge": "AMD ROCm OPTIMERAT",
        "hw.hero_title": "🚀 Kör AI-modeller lokalt på din egen GPU",
        "hw.hero_desc": "Med AgentFarm och rätt hårdvara kan du köra LLaMA, Qwen, Mistral och andra open source-modeller helt privat - utan molntjänster eller månadsavgifter.",
        "hw.benefit_private": "100% privat - ingen data lämnar din dator",
        "hw.benefit_cost": "Engångskostnad - inga API-avgifter",
        "hw.benefit_speed": "Snabb inference - 50+ tokens/sek",
        "hw.my_stack": "⚡ MIN STACK",
        "hw.my_stack_desc": "Hårdvaran som driver AgentFarm",
        "hw.buy_amazon": "Köp på Amazon.se →",
        "hw.loading": "LADDAR PRODUKTER",
        "hw.no_products": "INGA PRODUKTER",
        "hw.info_title": "🎯 VARFÖR AMD FÖR AI/ML?",
        "hw.info_rocm": "🔧 ROCm 6.x SUPPORT",
        "hw.info_rocm_desc": "Full PyTorch och TensorFlow-kompatibilitet via ROCm. Kör lokala LLMs utan CUDA-beroende - helt open source.",
        "hw.info_vram": "💾 VRAM ÄR NYCKELN",
        "hw.info_vram_desc": "24GB VRAM på 7900 XTX klarar 70B-modeller med kvantisering. 16GB på 7800 XT räcker för de flesta 7B-13B modeller.",
        "hw.info_ubuntu": "🐧 UBUNTU 22.04 LTS",
        "hw.info_ubuntu_desc": "ROCm fungerar bäst på Ubuntu 22.04 LTS. Vi kör AgentFarm på exakt denna setup - testat och verifierat.",
        "hw.info_value": "💰 MER VRAM PER KRONA",
        "hw.info_value_desc": "AMD-kort ger ofta mer VRAM per krona jämfört med NVIDIA. Perfekt för hobbyprojekt, startups och privatpersoner.",
        "hw.try_title": "🤖 VILL DU TESTA AGENTERNA?",
        "hw.try_desc": "Prova AgentFarm gratis och se hur AI-agenter kan hjälpa dig skapa kod, tester och dokumentation.",
        "hw.try_btn": "PROVA NU - GRATIS",
        "hw.footer_affiliate": "🔗 Affiliate-länkar - vi får en liten provision om du köper via våra länkar. Det kostar dig inget extra!",
        "hw.footer_back": "← Tillbaka till AgentFarm",
    },

    en: {
        // Header
        "header.system": "SYSTEM",
        "header.online": "ONLINE",
        "header.agents": "AGENTS",
        "header.status": "STATUS",
        "header.guest": "GUEST",
        "header.synth": "SYNTH",

        // Section headers
        "section.neural_network": "NEURAL NETWORK",
        "section.data_stream": "DATA STREAM",
        "section.command_interface": "COMMAND INTERFACE",
        "section.workflow_status": "WORKFLOW STATUS",
        "section.token_metrics": "TOKEN METRICS",
        "section.project_files": "PROJECT FILES",
        "section.project_files_subtitle": "Files that agents can read",

        // Command input
        "input.placeholder": "Describe what you want to create...\n\nE.g: Create a Python function that validates email addresses with regex and returns True/False. Add unit tests.",
        "input.execute": "EXECUTE",
        "input.hint": "More details = better results · Ctrl+Enter to run",
        "input.multi_provider": "MULTI-PROVIDER MODE",

        // Workflow stages
        "stage.plan": "PLAN",
        "stage.ux": "UX",
        "stage.execute": "EXECUTE",
        "stage.verify": "VERIFY",
        "stage.review": "REVIEW",
        "stage.standby": "STANDBY",
        "stage.active": "ACTIVE",
        "stage.complete": "COMPLETE",
        "stage.error": "ERROR",
        "stage.skipped": "SKIPPED",

        // Launch button
        "launch.button": "LAUNCH PROJECT",
        "launch.path": "Path",

        // Token metrics
        "metrics.total_tokens": "TOTAL TOKENS",
        "metrics.avg_tps": "AVG TOKENS/SEC",
        "metrics.latency": "LATENCY (P95)",

        // File upload
        "files.info": "Upload files that agents can access: code files, documentation, specifications, etc.",
        "files.drop_here": "DROP FILES HERE",
        "files.click_hint": "or click to select files",
        "files.formats": ".py .js .ts .json .md .txt .yaml .csv .pdf",
        "files.beta_required": "BETA OPERATOR REQUIRED",
        "files.become_beta": "BECOME BETA OPERATOR",

        // Footer
        "footer.tagline": "NEURAL ORCHESTRATION SYSTEM",
        "footer.prompts": "YOUR PROMPTS",
        "footer.beta_operator": "BETA OPERATOR",
        "footer.feedback": "FEEDBACK",
        "footer.hardware": "HARDWARE",

        // File browser modal
        "browser.title": "PROJECT FILES",
        "browser.up": "UP",
        "browser.download": "DOWNLOAD",

        // Beta Operator modal
        "beta.title": "BECOME BETA OPERATOR",
        "beta.intro": "Unlock all premium features and help shape AgentFarm!",
        "beta.price": "29 SEK",
        "beta.price_period": "one-time payment",
        "beta.feature_workflows": "10 AI-powered workflows",
        "beta.feature_files": "File upload (SecureVault)",
        "beta.feature_prompts": "Custom system prompts",
        "beta.feature_feedback": "Direct feedback to developer",
        "beta.feature_vpn": "VPN access for secure connection",
        "beta.feature_zip": "ZIP download of projects",
        "beta.button": "BECOME BETA OPERATOR",
        "beta.disclaimer": "Instant access. Payment handled securely via Stripe.",

        // Privacy section
        "beta.privacy_title": "PRIVACY & DATA SECURITY",
        "beta.privacy_intro": "This service is built with \"Privacy by Design\" as a core principle. Your data is handled with the highest possible security standards.",
        "beta.privacy_airgap_title": "Total Isolation (Air-gapped)",
        "beta.privacy_airgap_desc": "Unlike cloud-based AI services, your data never leaves the local infrastructure. All processing occurs on dedicated hardware (AMD Radeon 7800 XT) that is logically isolated while agents work with your context.",
        "beta.privacy_vpn_title": "Encrypted Access",
        "beta.privacy_vpn_desc": "All communication occurs via a point-to-point encrypted WireGuard VPN tunnel. No outsider can see or intercept the data you share.",
        "beta.privacy_gdpr_title": "GDPR Compliance",
        "beta.privacy_gdpr_purpose": "We only collect data required to perform your tasks",
        "beta.privacy_gdpr_training": "Your data is never used to train the AI models",
        "beta.privacy_gdpr_delete": "When your session ends, your data is deleted from working memory and storage",
        "beta.privacy_nis2_title": "NIS2 & Cybersecurity",
        "beta.privacy_nis2_desc": "By using this local solution, you reduce exposure to third-party cloud risks, facilitating compliance with the NIS2 directive.",
        "beta.privacy_consent": "By completing the payment, you agree that your data will be handled according to the above security protocols.",

        // Tryout modal
        "tryout.title": "TRY AGENTFARM",
        "tryout.intro": "Test AI agents that create code for you - completely free!",
        "tryout.feature_agents": "6 specialized AI agents",
        "tryout.feature_workflow": "1 free workflow",
        "tryout.button": "START FREE",
        "tryout.disclaimer": "No registration. Like it? Upgrade to Beta Operator!",

        // Feedback modal
        "feedback.title": "SEND FEEDBACK",
        "feedback.category": "CATEGORY",
        "feedback.category_general": "General",
        "feedback.category_bug": "Bug",
        "feedback.category_feature": "New feature",
        "feedback.category_ux": "UX/Design",
        "feedback.category_performance": "Performance",
        "feedback.message": "MESSAGE",
        "feedback.message_placeholder": "Describe your feedback...",
        "feedback.email": "EMAIL (optional)",
        "feedback.email_placeholder": "your@email.com",
        "feedback.rating": "RATING (optional)",
        "feedback.submit": "SUBMIT",

        // Datastream modal
        "datastream.title": "ALL EVENTS",
        "datastream.no_events": "No events yet",
        "datastream.expand": "Expand",

        // Context modal
        "context.title": "COMPANY CONTEXT",
        "context.info": "Add background information about your company or project. Agents will take this into account in their responses.",
        "context.placeholder": "E.g: We are a startup building an app for...",
        "context.save": "SAVE",

        // Agent config modal
        "agents.title": "AGENT CONFIGURATION",
        "agents.info": "Customize each agent's behavior. Your additions are appended after the base prompt.",
        "agents.base_prompt": "BASE PROMPT:",
        "agents.your_addition": "YOUR ADDITION:",
        "agents.save_all": "SAVE ALL",
        "agents.clear_all": "CLEAR ALL",

        // Agent names and descriptions
        "agent.orchestrator": "ORCHESTRATOR",
        "agent.orchestrator_desc": "The brain of AgentFarm. Controls flow between agents, handles loop detection and quality gates.",
        "agent.planner": "PLANNER",
        "agent.planner_desc": "Chief architect. Breaks down problems into executable roadmap with sequential JSON plan.",
        "agent.ux_designer": "UX DESIGNER",
        "agent.ux_designer_desc": "Responsible for interfaces, API contracts and user flows. Follows 80s Sci-Fi aesthetic by default.",
        "agent.executor": "EXECUTOR",
        "agent.executor_desc": "Senior developer. Writes clean, secure code in isolated sandbox. Follows code styles from context.",
        "agent.verifier": "VERIFIER",
        "agent.verifier_desc": "QA engineer. Finds bugs, runs tests in sandbox, approves only if all tests pass.",
        "agent.reviewer": "REVIEWER",
        "agent.reviewer_desc": "Final review. Verifies that output matches requirements and ZIP export is secure.",

        // Placeholders
        "placeholder.orchestrator": "E.g: Prioritize speed over precision...",
        "placeholder.planner": "E.g: Always use microservices architecture...",
        "placeholder.ux_designer": "E.g: Use our design system with blue primary color...",
        "placeholder.executor": "E.g: Use TypeScript and write JSDoc comments...",
        "placeholder.verifier": "E.g: Require 80% code coverage...",
        "placeholder.reviewer": "E.g: Check that no API keys are in the code...",

        // Hardware page
        "hw.back": "BACK TO TERMINAL",
        "hw.title": "HARDWARE TERMINAL",
        "hw.subtitle": "BUILD YOUR OWN AI COMPUTER - RUN LLMs LOCALLY",
        "hw.rocm_badge": "AMD ROCm OPTIMIZED",
        "hw.hero_title": "🚀 Run AI models locally on your own GPU",
        "hw.hero_desc": "With AgentFarm and the right hardware, you can run LLaMA, Qwen, Mistral and other open source models completely privately - no cloud services or monthly fees.",
        "hw.benefit_private": "100% private - no data leaves your computer",
        "hw.benefit_cost": "One-time cost - no API fees",
        "hw.benefit_speed": "Fast inference - 50+ tokens/sec",
        "hw.my_stack": "⚡ MY STACK",
        "hw.my_stack_desc": "The hardware that powers AgentFarm",
        "hw.buy_amazon": "Buy on Amazon.se →",
        "hw.loading": "LOADING PRODUCTS",
        "hw.no_products": "NO PRODUCTS",
        "hw.info_title": "🎯 WHY AMD FOR AI/ML?",
        "hw.info_rocm": "🔧 ROCm 6.x SUPPORT",
        "hw.info_rocm_desc": "Full PyTorch and TensorFlow compatibility via ROCm. Run local LLMs without CUDA dependency - completely open source.",
        "hw.info_vram": "💾 VRAM IS KEY",
        "hw.info_vram_desc": "24GB VRAM on 7900 XTX handles 70B models with quantization. 16GB on 7800 XT is enough for most 7B-13B models.",
        "hw.info_ubuntu": "🐧 UBUNTU 22.04 LTS",
        "hw.info_ubuntu_desc": "ROCm works best on Ubuntu 22.04 LTS. We run AgentFarm on this exact setup - tested and verified.",
        "hw.info_value": "💰 MORE VRAM PER DOLLAR",
        "hw.info_value_desc": "AMD cards often give more VRAM per dollar compared to NVIDIA. Perfect for hobby projects, startups and individuals.",
        "hw.try_title": "🤖 WANT TO TEST THE AGENTS?",
        "hw.try_desc": "Try AgentFarm for free and see how AI agents can help you create code, tests and documentation.",
        "hw.try_btn": "TRY NOW - FREE",
        "hw.footer_affiliate": "🔗 Affiliate links - we get a small commission if you buy through our links. It costs you nothing extra!",
        "hw.footer_back": "← Back to AgentFarm",
    }
};

// Current language state
let currentLanguage = localStorage.getItem('agentfarm_lang') || 'sv';

/**
 * Get translation for a key
 */
function t(key) {
    return TRANSLATIONS[currentLanguage]?.[key] || TRANSLATIONS['sv'][key] || key;
}

/**
 * Set the current language and update UI
 */
function setLanguage(lang) {
    if (!TRANSLATIONS[lang]) return;

    currentLanguage = lang;
    localStorage.setItem('agentfarm_lang', lang);
    document.documentElement.lang = lang;

    // Update toggle buttons
    document.querySelectorAll('.lang-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.lang === lang);
    });

    // Apply translations to page
    applyTranslations();
}

/**
 * Apply all translations to the page
 */
function applyTranslations() {
    // Update all elements with data-i18n attribute
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.dataset.i18n;
        el.textContent = t(key);
    });

    // Update all elements with data-i18n-placeholder attribute
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.dataset.i18nPlaceholder;
        el.placeholder = t(key);
    });

    // Update all elements with data-i18n-title attribute
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        const key = el.dataset.i18nTitle;
        el.title = t(key);
    });
}

/**
 * Initialize language toggle
 */
function initLanguageToggle() {
    // Set initial language from localStorage
    document.documentElement.lang = currentLanguage;

    // Wire up toggle buttons
    document.querySelectorAll('.lang-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            setLanguage(btn.dataset.lang);
        });
        // Set initial active state
        btn.classList.toggle('active', btn.dataset.lang === currentLanguage);
    });

    // Apply translations on load
    applyTranslations();
}

// Export for use in app.js
window.i18n = {
    t,
    setLanguage,
    applyTranslations,
    initLanguageToggle,
    getCurrentLanguage: () => currentLanguage
};
