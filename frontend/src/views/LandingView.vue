<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

async function handleLogout() {
  await auth.logout()
  router.push('/login')
}

const scrolled = ref(false)
const onScroll = () => { scrolled.value = window.scrollY > 24 }

// Interactive Hero Workbench showcase (cycles automatically or on click)
const heroScenarios = [
  {
    id: 'rates',
    tab: 'Hourly Rates',
    doc: 'Invoice_Mar2026.pdf',
    page: 'Page 1 · Table Row 01',
    bboxLabel: 'EXTRACTED RATE CLAIM',
    rawLines: [
      { text: 'Billing Period: March 1, 2026 – March 31, 2026', highlight: false },
      { text: '01  Principal Cloud Architect   160 hrs   $250.00 / hr   $40,000', highlight: true },
      { text: '02  Senior Data Engineer        160 hrs   $185.00 / hr   $29,600', highlight: false },
    ],
    verdictStatus: 'CONFLICT',
    severity: 'HIGH SEVERITY',
    title: 'Architect Rate Exceeds MSA Ceiling',
    delta: '+$40/hr ($6,400 overcharge)',
    comparison: [
      { source: 'MSA §2.3 · p.2', value: '$210.00 / hr cap', tone: 'neutral' },
      { source: 'SOW §2.0 · p.1', value: '$225.00 / hr (no CLO sign)', tone: 'warn' },
      { source: 'Invoice · p.1', value: '$250.00 / hr billed', tone: 'bad' },
    ],
  },
  {
    id: 'payment',
    tab: 'Payment Terms',
    doc: 'SOW_ProjectAtlas.pdf',
    page: 'Page 1 · Section 3.2',
    bboxLabel: 'EXTRACTED PAYMENT WINDOW',
    rawLines: [
      { text: '3.1. Vendor shall submit monthly invoices on the last business day.', highlight: false },
      { text: '3.2. Payment Schedule. Invoices payable on Net 30 · 2.0% late fee.', highlight: true },
      { text: '3.3. Onsite Travel reimbursed up to $6,500/mo without prior auth.', highlight: false },
    ],
    verdictStatus: 'CONFLICT',
    severity: 'HIGH SEVERITY',
    title: 'Unauthorized Payment Window Shortening',
    delta: 'Net 45 → Net 30 → Net 15',
    comparison: [
      { source: 'MSA §2.1 · p.1', value: 'Net 45 · 1.0% interest', tone: 'neutral' },
      { source: 'SOW §3.2 · p.1', value: 'Net 30 · 2.0% late fee', tone: 'warn' },
      { source: 'Invoice · p.1', value: 'Net 15 · 3.0% + suspension', tone: 'bad' },
    ],
  },
  {
    id: 'budget',
    tab: 'NTE Budget Cap',
    doc: 'CO_2026_01A.pdf',
    page: 'Page 1 · Section 2.2',
    bboxLabel: 'CUMULATIVE SPEND CHECK',
    rawLines: [
      { text: '2.1. Timeline Extension. Phase 2 extended to May 15, 2026.', highlight: false },
      { text: '2.2. Budget Adjustment. Revised total NTE cap is $225,000.00.', highlight: true },
      { text: 'Signed: David Chen (Client) & Raj Patel (Vendor), Mar 10, 2026.', highlight: false },
    ],
    verdictStatus: 'CONFLICT',
    severity: 'HIGH SEVERITY',
    title: 'Cumulative Billed Exceeds Revised NTE',
    delta: '$19,960.00 over cap',
    comparison: [
      { source: 'SOW §2 · p.1', value: '$185,000.00 original NTE', tone: 'neutral' },
      { source: 'CO §2.2 · p.1', value: '$225,000.00 revised NTE', tone: 'ok' },
      { source: 'Invoice · p.2', value: '$244,960.00 cumulative', tone: 'bad' },
    ],
  },
]

const activeScenarioIdx = ref(0)
const activeScenario = computed(() => heroScenarios[activeScenarioIdx.value])
let scenarioTimer = null

function selectScenario(idx) {
  activeScenarioIdx.value = idx
  if (scenarioTimer) clearInterval(scenarioTimer)
  scenarioTimer = setInterval(() => {
    activeScenarioIdx.value = (activeScenarioIdx.value + 1) % heroScenarios.length
  }, 4800)
}

let observer
onMounted(() => {
  window.addEventListener('scroll', onScroll, { passive: true })
  observer = new IntersectionObserver(
    (entries) => entries.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('in'); observer.unobserve(e.target) } }),
    { threshold: 0.12 }
  )
  document.querySelectorAll('.reveal').forEach((el) => observer.observe(el))
  scenarioTimer = setInterval(() => {
    activeScenarioIdx.value = (activeScenarioIdx.value + 1) % heroScenarios.length
  }, 4800)
})

onUnmounted(() => {
  window.removeEventListener('scroll', onScroll)
  observer?.disconnect()
  if (scenarioTimer) clearInterval(scenarioTimer)
})

const mode = ref('sd')
const board = [
  { metric: 'Documents compared', hand: ['SAMPLED', 'PARTIAL'], sd: ['ALL', 'CROSS-LINKED'] },
  { metric: 'Claims with a source', hand: ['SOME', 'MISSING'], sd: ['EVERY', 'CLAIM CITED'] },
  { metric: 'Conflicts found', hand: ['WHAT WAS', 'NOTICED'], sd: ['CLUSTERED', 'BY TOPIC'] },
  { metric: 'Clean corpus result', hand: ['UNCLEAR', 'UNCLEAR'], sd: ['NO FINDINGS', 'REPORTED'] },
]
const flaps = (txt) => txt.padEnd(12, ' ').split('')
const rows = computed(() => board.map((r) => ({ metric: r.metric, value: r[mode.value][0], status: r[mode.value][1] })))

const steps = [
  { n: '01', title: 'Ingest', text: 'Upload related PDFs. Each is parsed into text, tables and structure, preserving page numbers and bounding context.' },
  { n: '02', title: 'Extract', text: 'Atomic claims, rates, dates, caps, and governance override rules are decomposed cleanly from every section.' },
  { n: '03', title: 'Judge', text: 'Cross-document topic clusters go to a reasoning judge that returns CONFLICT or AGREEMENT with verbatim quotes.' },
  { n: '04', title: 'Decide', text: 'Conflicts queue for human sign-off while agreements commit automatically into one audit-ready deliverable.' },
]

const pillars = [
  { n: '01', label: 'Problem', title: 'Documents drift. Nobody notices until it costs money.', text: 'An amendment changes a rate, an invoice ignores it, a baseline still says the old thing. Finding that by hand means reading every page against every other page.', list: ['Amendments silently supersede clauses', 'Invoices contradict agreed terms', 'Reviewers sample instead of read'] },
  { n: '02', label: 'Solution', title: 'Compare everything. Cite everything.', text: 'SuperDocs links related passages across the whole set, asks a reasoning judge to compare them, and keeps the exact quote and page behind every statement.', list: ['Multi-document atomic topic clustering', 'Governance & precedence-aware conflict detection', 'Human sign-off before anything is committed'] },
  { n: '03', label: 'Impact', title: 'One deliverable you can defend.', text: 'Resolved conflicts and agreed clauses combine into a single register. If the corpus is clean, you get an honest report of no findings.', list: ['Audit-ready source trail on every line', 'Faster review cycles with zero hallucinations', 'Verifiable compliance against your source of truth'] },
]

const faqs = [
  { q: 'What is SuperDocs?', a: 'SuperDocs is an agentic document reconciliation platform. It ingests related documents, finds where they disagree, and produces one grounded report where every claim points to the exact page and quote it came from.' },
  { q: 'How many documents can I compare?', a: 'From two upwards. Related passages are linked across the entire set, so a clause in one document can be compared with matching clauses and line items across all the others at once.' },
  { q: 'Does it replace our reviewers?', a: 'No. The system does the reading, extraction, and cross-checking. Conflicts go to a Human Review Gate where your team approves, rewrites, or rejects each finding.' },
  { q: 'What file types are supported?', a: 'PDF documents with full text and structured table extraction, preserving exact page numbers and section context.' },
  { q: 'What if the documents all agree?', a: 'You get a report of no findings, with the agreed clauses and their citations. Nothing is manufactured to look busy.' },
]
</script>

<template>
  <div class="landing">
    <header class="nav" :class="{ scrolled }">
      <RouterLink to="/" class="brand" id="nav-brand" aria-label="SuperDocs home">
        <svg width="26" height="26" viewBox="0 0 26 26" fill="none" aria-hidden="true">
          <rect x="3" y="2" width="14" height="18" rx="2" stroke="#09090B" stroke-width="1.6"/>
          <rect x="9" y="6" width="14" height="18" rx="2" fill="#FFFFFF" stroke="#09090B" stroke-width="1.6"/>
          <path d="M12.5 12h7M12.5 15.5h7M12.5 19h4" stroke="#09090B" stroke-width="1.4" stroke-linecap="round"/>
        </svg>
        <span>SuperDocs</span>
      </RouterLink>
      <nav class="nav-links" aria-label="Primary">
        <a href="#what" id="nav-what">Platform</a>
        <a href="#how" id="nav-how">How it works</a>
        <a href="#report" id="nav-report">Sample report</a>
        <a href="#faq" id="nav-faq">FAQ</a>
      </nav>
      <div class="nav-auth">
        <template v-if="auth.user">
          <RouterLink to="/app" class="nav-login" id="nav-workspace">Workspace</RouterLink>
          <button class="btn btn-accent sm" @click="handleLogout" id="nav-logout">Log out</button>
        </template>
        <template v-else>
          <RouterLink to="/login" class="nav-login" id="nav-login">Log in</RouterLink>
          <RouterLink to="/signup" class="btn btn-accent sm" id="nav-signup">Get started</RouterLink>
        </template>
      </div>
    </header>

    <main>
      <!-- HERO (Reducto-inspired light editorial canvas + vibrant magenta accent + live animated workbench) -->
      <section class="hero">
        <div class="hero-grid-bg" aria-hidden="true"></div>
        <div class="hero-glow" aria-hidden="true"></div>

        <div class="container hero-in">
          <div class="hero-eyebrow reveal">
            <span class="pulse-dot"></span>
            <span class="label">Agentic Document Reconciliation · Every Claim Cited</span>
          </div>

          <h1 class="display hero-title reveal">
            Document <span class="serif-accent accent-word">Reconciliation</span>
            <br />that never misses a clause.
          </h1>

          <p class="body-lg hero-sub reveal">
            SuperDocs reads piles of related contracts, amendments, and invoices, pinpoints every contradiction with exact page citations, and builds one grounded report your team signs off on.
          </p>

          <div class="hero-cta reveal">
            <RouterLink :to="auth.user ? '/app' : '/signup'" class="btn btn-accent" id="hero-signup">
              {{ auth.user ? 'Open Workspace' : 'Start reconciling free' }}
              <span aria-hidden="true">→</span>
            </RouterLink>
            <a href="#how" class="btn btn-outline" id="hero-how">See how it works</a>
          </div>

          <!-- Interactive Animated Document-to-Conflict Workbench -->
          <div class="workbench reveal">
            <div class="wb-topbar">
              <div class="wb-dots" aria-hidden="true">
                <span></span><span></span><span></span>
              </div>
              <div class="wb-tabs" role="tablist" aria-label="Sample reconciliation scenarios">
                <button
                  v-for="(sc, idx) in heroScenarios"
                  :key="sc.id"
                  type="button"
                  role="tab"
                  class="wb-tab"
                  :class="{ active: activeScenarioIdx === idx }"
                  :aria-selected="activeScenarioIdx === idx"
                  @click="selectScenario(idx)"
                >
                  {{ sc.tab }}
                </button>
              </div>
              <span class="wb-live-pill">
                <span class="wb-live-dot"></span>
                100% Grounded
              </span>
            </div>

            <div class="wb-body">
              <!-- Left: Source Document Scanner -->
              <div class="wb-pane wb-source">
                <div class="wb-pane-head">
                  <span class="label muted">{{ activeScenario.doc }}</span>
                  <span class="wb-page-pill">{{ activeScenario.page }}</span>
                </div>

                <div class="doc-canvas">
                  <div class="scan-beam" aria-hidden="true"></div>
                  <div
                    v-for="(line, lIdx) in activeScenario.rawLines"
                    :key="activeScenario.id + '-' + lIdx"
                    class="doc-line"
                    :class="{ bbox: line.highlight }"
                  >
                    <span v-if="line.highlight" class="bbox-tag">{{ activeScenario.bboxLabel }}</span>
                    <code>{{ line.text }}</code>
                  </div>
                </div>
              </div>

              <!-- Center: Animated Pipeline Flow -->
              <div class="wb-bridge" aria-hidden="true">
                <div class="bridge-line"></div>
                <div class="bridge-node">
                  <span>01</span>
                  <small>Extract</small>
                </div>
                <div class="bridge-node active">
                  <span>02</span>
                  <small>Judge</small>
                </div>
                <div class="bridge-node">
                  <span>03</span>
                  <small>Cite</small>
                </div>
              </div>

              <!-- Right: Grounded Conflict Card -->
              <div class="wb-pane wb-output" :key="activeScenario.id">
                <div class="wb-pane-head">
                  <div class="wb-badges">
                    <span class="wb-badge-conflict">{{ activeScenario.verdictStatus }}</span>
                    <span class="wb-badge-sev">{{ activeScenario.severity }}</span>
                  </div>
                  <span class="wb-delta">{{ activeScenario.delta }}</span>
                </div>

                <h3 class="wb-verdict-title">{{ activeScenario.title }}</h3>

                <div class="wb-compare-list">
                  <div
                    v-for="(item, cIdx) in activeScenario.comparison"
                    :key="cIdx"
                    class="wb-compare-row"
                    :class="item.tone"
                  >
                    <span class="wb-src">{{ item.source }}</span>
                    <strong class="wb-val">{{ item.value }}</strong>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- WHAT IS -->
      <section id="what" class="band">
        <div class="container">
          <div class="frame two-col reveal">
            <div class="cell side"><h2 class="label accent-label">What is SuperDocs?</h2></div>
            <div class="cell">
              <p class="what-text">
                SuperDocs is a document reconciliation platform for teams that manage contracts, amendments, and invoices.
                It understands the pile, extracts atomic facts, surfaces every disagreement, and produces one deliverable where every claim
                traces back to its exact source page.
              </p>
              <div class="links">
                <a href="#how">Atomic ingestion</a>
                <a href="#how">Governance-aware judge</a>
                <a href="#report">Grounded reports</a>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- STATUS BOARD -->
      <section class="board-sec">
        <div class="container">
          <div class="board-top reveal">
            <div>
              <span class="label accent-on-dark">Status board</span>
              <h2 class="h2 on-dark">Same documents. <span class="serif-accent">Different certainty.</span></h2>
            </div>
            <div class="toggle" role="group" aria-label="Compare the board">
              <button type="button" id="toggle-hand" :class="{ on: mode === 'hand' }" :aria-pressed="mode === 'hand'" @click="mode = 'hand'">By hand</button>
              <button type="button" id="toggle-sd" :class="{ on: mode === 'sd' }" :aria-pressed="mode === 'sd'" @click="mode = 'sd'">With SuperDocs</button>
            </div>
          </div>
          <div class="board reveal">
            <div class="brow head"><span>Metric</span><span>Now showing</span><span>Status</span></div>
            <div v-for="r in rows" :key="r.metric" class="brow">
              <span class="metric">{{ r.metric }}</span>
              <span class="flaps" :class="mode"><span v-for="(c, i) in flaps(r.value)" :key="mode + i" class="flap" :style="{ animationDelay: i * 22 + 'ms' }">{{ c }}</span></span>
              <span class="flaps status" :class="mode"><span v-for="(c, i) in flaps(r.status)" :key="mode + i" class="flap" :style="{ animationDelay: i * 22 + 'ms' }">{{ c }}</span></span>
            </div>
          </div>
          <p class="label note">Illustrative comparison of manual review versus the SuperDocs agentic workflow.</p>
        </div>
      </section>

      <!-- MANIFESTO -->
      <section class="band">
        <div class="container">
          <div class="frame two-col reveal">
            <div class="cell side"><span class="label accent-label">Our belief</span></div>
            <div class="cell">
              <p class="h3 manifesto">A contract is a promise. Reconciliation is where you find out whether every document <span class="serif-accent accent-word">agrees</span> — or <span class="serif-accent accent-word">doesn't</span>.</p>
              <a href="#how" class="underline">See how it works →</a>
            </div>
          </div>
        </div>
      </section>

      <!-- PROBLEM / SOLUTION / IMPACT -->
      <section class="band tight">
        <div class="container">
          <article v-for="p in pillars" :key="p.n" class="frame two-col pillar reveal">
            <div class="cell side">
              <span class="label tag-n">{{ p.n }}</span>
              <span class="label accent-label">{{ p.label }}</span>
            </div>
            <div class="cell">
              <h2 class="h2">{{ p.title }}</h2>
              <p class="body-lg soft">{{ p.text }}</p>
              <ul class="list">
                <li v-for="l in p.list" :key="l">{{ l }}</li>
              </ul>
            </div>
          </article>
        </div>
      </section>

      <!-- HOW IT WORKS -->
      <section id="how" class="how">
        <div class="container">
          <div class="how-head reveal">
            <span class="label accent-on-dark">How it works</span>
            <h2 class="h2 on-dark">From a pile of PDFs to <span class="serif-accent">one answer</span></h2>
          </div>
          <div class="steps">
            <article v-for="s in steps" :key="s.n" class="step reveal">
              <span class="label accent-on-dark">{{ s.n }}</span>
              <h3>{{ s.title }}</h3>
              <p>{{ s.text }}</p>
            </article>
          </div>
        </div>
      </section>

      <!-- REPORT -->
      <section id="report" class="band">
        <div class="container">
          <div class="rep-head reveal">
            <span class="label accent-label">Sample deliverable</span>
            <h2 class="h2">A register where every row is <span class="serif-accent accent-word">sourced</span></h2>
          </div>
          <div class="frame table-wrap reveal">
            <table>
              <thead>
                <tr><th>Clause</th><th>Baseline (MSA)</th><th>Amendment / SOW</th><th>Invoice</th><th>Committed</th></tr>
              </thead>
              <tbody>
                <tr><td>Principal Cloud Architect</td><td>$210 / hr</td><td class="neg">$225 / hr</td><td class="neg">$250 / hr</td><td class="pos">$210 / hr</td></tr>
                <tr><td>Payment Terms</td><td>Net 45</td><td class="neg">Net 30</td><td class="neg">Net 15</td><td class="pos">Net 45</td></tr>
                <tr><td>Cumulative NTE Budget</td><td>$185,000</td><td>$225,000 (CO)</td><td class="neg">$244,960</td><td class="pos">$225,000 cap</td></tr>
                <tr><td>Performance Warranty</td><td>90 days</td><td class="neg">30 days (ETL)</td><td>n/a</td><td class="pos">90 days</td></tr>
              </tbody>
            </table>
          </div>
          <blockquote class="quote reveal">
            <span class="label">Invoice · Page 1 · flagged</span>
            “01 Principal Cloud Architect (A. Sterling) — 160 hrs @ $250.00 / hr = $40,000.00”
          </blockquote>
        </div>
      </section>

      <!-- FAQ -->
      <section id="faq" class="band tight">
        <div class="container">
          <div class="frame two-col reveal">
            <div class="cell side"><h2 class="label accent-label">Questions</h2></div>
            <div class="cell faq">
              <details v-for="f in faqs" :key="f.q">
                <summary>{{ f.q }}<span aria-hidden="true">+</span></summary>
                <p>{{ f.a }}</p>
              </details>
            </div>
          </div>
        </div>
      </section>

      <!-- CTA -->
      <section class="final">
        <div class="container reveal">
          <h2 class="display sm-display">Stop hunting for <span class="serif-accent accent-on-dark">contradictions.</span></h2>
          <p class="body-lg">Create an account and run your first grounded reconciliation.</p>
          <div class="hero-cta center">
            <template v-if="auth.user">
              <RouterLink to="/app" class="btn btn-accent" id="cta-workspace">Open Workspace →</RouterLink>
              <button class="btn btn-outline-dark" @click="handleLogout" id="cta-logout">Log out</button>
            </template>
            <template v-else>
              <RouterLink to="/signup" class="btn btn-accent" id="cta-signup">Get started →</RouterLink>
              <RouterLink to="/login" class="btn btn-outline-dark" id="cta-login">Log in</RouterLink>
            </template>
          </div>
        </div>
      </section>
    </main>

    <footer class="footer">
      <div class="container foot-in">
        <span class="brand-sm">SuperDocs</span>
        <small>© {{ new Date().getFullYear() }} SuperDocs. Grounded document intelligence.</small>
      </div>
    </footer>
  </div>
</template>

<style scoped>
/* NAV */
.nav {
  position: fixed; inset: 0 0 auto 0; z-index: 50; height: 68px;
  display: grid; grid-template-columns: 1fr auto 1fr; align-items: center;
  padding: 0 clamp(20px, 3vw, 44px);
  border-bottom: 1px solid transparent;
  transition: background .25s ease, border-color .25s ease, box-shadow .25s ease;
}
.nav.scrolled {
  background: rgba(255, 255, 255, 0.90);
  backdrop-filter: blur(14px);
  border-color: var(--hairline);
  box-shadow: 0 4px 20px rgba(9, 9, 11, 0.04);
}
.brand { display: inline-flex; align-items: center; gap: 10px; color: var(--ink); font-size: 18px; font-weight: 600; letter-spacing: -0.02em; }
.nav-links { display: flex; gap: 4px; }
.nav-links a { padding: 7px 14px; font-size: 14.5px; font-weight: 500; color: var(--ink-soft); border-radius: 999px; transition: color .15s, background .15s; }
.nav-links a:hover { color: var(--ink); background: var(--paper-deep); }
.nav-auth { display: flex; align-items: center; justify-content: flex-end; gap: 16px; }
.nav-login { color: var(--ink-soft); font-size: 14.5px; font-weight: 500; transition: color .15s; }
.nav-login:hover { color: var(--ink); }
.btn.sm { padding: 9px 18px; font-size: 13.5px; }

/* HERO */
.hero {
  position: relative;
  background: var(--surface);
  padding: clamp(118px, 10vw, 152px) 0 clamp(68px, 7vw, 104px);
  overflow: hidden;
  border-bottom: 1px solid var(--hairline);
}
.hero-grid-bg {
  position: absolute; inset: 0; pointer-events: none;
  background-image: radial-gradient(rgba(9, 9, 11, 0.12) 1px, transparent 1px);
  background-size: 26px 26px;
  mask-image: radial-gradient(ellipse 80% 70% at 50% 35%, #000 35%, transparent 100%);
}
.hero-glow {
  position: absolute; top: -140px; left: 50%; transform: translateX(-50%);
  width: min(980px, 110vw); height: 420px; pointer-events: none;
  background: radial-gradient(ellipse at center, rgba(9, 9, 11, 0.05) 0%, transparent 70%);
}
.hero-in { position: relative; z-index: 1; text-align: center; }

.hero-eyebrow {
  display: inline-flex; align-items: center; gap: 10px;
  padding: 7px 16px; border-radius: 999px;
  background: var(--paper);
  border: 1px solid var(--hairline-strong);
  color: var(--ink);
  box-shadow: var(--shadow-sm);
  margin-bottom: 24px;
}
.pulse-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--ink);
  box-shadow: 0 0 0 4px rgba(9, 9, 11, 0.10);
  animation: pulse 2s ease-in-out infinite;
}

.hero-title { color: var(--ink); max-width: 960px; margin: 0 auto; }
.accent-word { color: var(--accent); }
.hero-sub { color: var(--ink-soft); max-width: 640px; margin: 24px auto 0; text-wrap: balance; }
.hero-cta { display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; margin-top: 34px; }

/* INTERACTIVE HERO WORKBENCH */
.workbench {
  margin: clamp(46px, 6vw, 68px) auto 0;
  max-width: 1020px;
  background: var(--surface);
  border: 1px solid var(--hairline-strong);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
  text-align: left;
}
.wb-topbar {
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  padding: 12px 18px;
  background: var(--paper-deep);
  border-bottom: 1px solid var(--hairline);
  flex-wrap: wrap;
}
.wb-dots { display: flex; gap: 6px; }
.wb-dots span { width: 9px; height: 9px; border-radius: 50%; background: rgba(38, 5, 39, 0.16); }
.wb-tabs { display: flex; gap: 4px; background: rgba(38, 5, 39, 0.05); padding: 3px; border-radius: 999px; }
.wb-tab {
  border: none; background: transparent; padding: 6px 14px; border-radius: 999px;
  font-family: var(--font-mono); font-size: 11px; letter-spacing: 0.04em;
  color: var(--ink-soft); cursor: pointer; transition: all .2s ease;
}
.wb-tab:hover { color: var(--ink); }
.wb-tab.active {
  background: var(--surface); color: var(--accent); font-weight: 500;
  box-shadow: 0 1px 4px rgba(38, 5, 39, 0.10);
}
.wb-live-pill {
  display: inline-flex; align-items: center; gap: 6px;
  font-family: var(--font-mono); font-size: 10.5px; letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--success); background: var(--success-soft); padding: 4px 10px; border-radius: 999px;
}
.wb-live-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--success); animation: pulse 1.8s infinite; }

.wb-body {
  display: grid;
  grid-template-columns: 1.05fr 84px 1fr;
  align-items: stretch;
}
.wb-pane { padding: 22px 24px; display: flex; flex-direction: column; gap: 16px; }
.wb-source { background: #FCFCFA; border-right: 1px solid var(--hairline); }
.wb-output { background: var(--surface); border-left: 1px solid var(--hairline); animation: fadeSlideUp .35s ease; }

.wb-pane-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
.muted { color: var(--ink-faint); }
.wb-page-pill {
  font-family: var(--font-mono); font-size: 10.5px; color: var(--ink-soft);
  background: var(--paper-deep); padding: 3px 9px; border-radius: 999px;
}

.doc-canvas {
  position: relative; overflow: hidden;
  background: var(--surface);
  border: 1px solid var(--hairline);
  border-radius: var(--radius-sm);
  padding: 16px;
  display: flex; flex-direction: column; gap: 10px;
}
.scan-beam {
  position: absolute; left: 0; right: 0; height: 34px;
  background: linear-gradient(180deg, transparent, rgba(9, 9, 11, 0.08), transparent);
  border-bottom: 1.5px solid rgba(9, 9, 11, 0.45);
  pointer-events: none;
  animation: scanBeam 3.6s ease-in-out infinite;
}
@keyframes scanBeam {
  0% { top: -34px; opacity: 0; }
  12% { opacity: 1; }
  88% { opacity: 1; }
  100% { top: 100%; opacity: 0; }
}

.doc-line {
  position: relative;
  padding: 9px 11px;
  border-radius: 5px;
  font-family: var(--font-mono); font-size: 11.5px; line-height: 1.45;
  color: var(--ink-soft);
  border: 1px solid transparent;
  transition: all .3s ease;
}
.doc-line.bbox {
  background: var(--paper-deep);
  border: 1.5px solid var(--ink);
  color: var(--ink);
  font-weight: 500;
  padding-top: 20px;
  box-shadow: 0 0 0 4px rgba(9, 9, 11, 0.05);
}
.bbox-tag {
  position: absolute; top: -1px; left: -1px;
  background: var(--ink); color: #fff;
  font-size: 9px; letter-spacing: 0.1em; padding: 2px 7px;
  border-radius: 4px 0 4px 0;
}

/* Center pipeline connector */
.wb-bridge {
  position: relative;
  background: var(--paper);
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px;
  padding: 16px 8px;
}
.bridge-line {
  position: absolute; top: 18%; bottom: 18%; left: 50%; width: 1.5px;
  background: linear-gradient(180deg, transparent, rgba(9, 9, 11, 0.25), transparent);
}
.bridge-node {
  position: relative; z-index: 1;
  width: 58px; padding: 7px 4px; border-radius: 8px;
  background: var(--surface); border: 1px solid var(--hairline-strong);
  display: flex; flex-direction: column; align-items: center; gap: 2px;
  font-family: var(--font-mono);
}
.bridge-node span { font-size: 10px; color: var(--accent); font-weight: 600; }
.bridge-node small { font-size: 9px; color: var(--ink-soft); text-transform: uppercase; letter-spacing: 0.05em; }
.bridge-node.active {
  border-color: var(--accent);
  background: var(--accent);
  box-shadow: 0 0 0 5px var(--accent-soft);
}
.bridge-node.active span, .bridge-node.active small { color: #fff; }

/* Output pane */
.wb-badges { display: flex; gap: 6px; }
.wb-badge-conflict {
  font-family: var(--font-mono); font-size: 10px; font-weight: 600; letter-spacing: 0.08em;
  background: var(--danger); color: #fff; padding: 3px 8px; border-radius: 4px;
}
.wb-badge-sev {
  font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.06em;
  background: var(--danger-soft); color: var(--danger); padding: 3px 8px; border-radius: 4px;
}
.wb-delta { font-family: var(--font-mono); font-size: 11px; color: var(--accent); font-weight: 600; }
.wb-verdict-title { font-family: var(--font-serif); font-size: 1.25rem; font-weight: 500; color: var(--ink); letter-spacing: -0.02em; }
.wb-compare-list { display: flex; flex-direction: column; gap: 8px; }
.wb-compare-row {
  display: flex; justify-content: space-between; align-items: center; gap: 10px;
  padding: 10px 12px; border-radius: 6px;
  background: var(--paper); border-left: 3px solid var(--hairline-strong);
  font-size: 12.5px;
}
.wb-compare-row.warn { border-left-color: var(--accent); background: var(--accent-soft); }
.wb-compare-row.bad { border-left-color: var(--danger); background: var(--danger-soft); }
.wb-compare-row.ok { border-left-color: var(--success); background: var(--success-soft); }
.wb-src { font-family: var(--font-mono); font-size: 11px; color: var(--ink-soft); }
.wb-val { font-family: var(--font-mono); font-size: 12px; color: var(--ink); font-weight: 500; }

/* BANDS / FRAMES */
.band { padding: clamp(52px, 7vw, 84px) 0; }
.band.tight { padding-top: 0; }
.two-col { display: grid; grid-template-columns: 280px 1fr; gap: 1px; background: var(--hairline); overflow: hidden; }
.cell { background: var(--surface); padding: 36px 40px 40px; }
.cell.side { background: #FCFCFA; padding: 36px 32px; display: flex; flex-direction: column; gap: 14px; align-items: flex-start; }
.accent-label { color: var(--accent); font-weight: 600; }
.accent-on-dark { color: var(--accent-light); }
.what-text { font-size: 18px; line-height: 1.65; letter-spacing: -0.01em; max-width: 700px; color: var(--ink); }
.links { display: flex; flex-wrap: wrap; gap: 10px 18px; margin-top: 22px; }
.links a, .underline { font-size: 14px; font-weight: 500; color: var(--accent); border-bottom: 1px solid rgba(157, 23, 160, 0.3); padding-bottom: 2px; transition: border-color .2s; }
.links a:hover, .underline:hover { border-color: var(--accent); }
.underline { display: inline-block; margin-top: 28px; font-size: 15px; }
.manifesto { max-width: 720px; }
.pillar { margin-bottom: 20px; transition: transform .25s ease, box-shadow .25s ease; }
.pillar:hover { transform: translateY(-2px); box-shadow: var(--shadow-md); }
.pillar .cell:not(.side) { display: grid; gap: 18px; }
.pillar .h2 { max-width: 580px; }
.soft { color: var(--ink-soft); max-width: 540px; }
.tag-n { padding: 5px 9px; border-radius: 4px; background: var(--ink); color: #fff; }
.list { list-style: none; display: grid; gap: 9px; }
.list li { padding-left: 22px; position: relative; font-size: 15px; color: var(--ink); }
.list li::before { content: ''; position: absolute; left: 0; top: .62em; width: 10px; height: 2px; background: var(--accent); border-radius: 2px; }

/* BOARD */
.board-sec { background: var(--dark); color: var(--cream); padding: clamp(68px, 9vw, 116px) 0; }
.board-top { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: 22px; margin-bottom: clamp(28px, 4vw, 48px); }
.on-dark { color: var(--cream); margin-top: 14px; max-width: 640px; }
.toggle { display: inline-flex; padding: 4px; border-radius: 999px; border: 1px solid var(--hairline-dark); background: rgba(248, 248, 246, .04); }
.toggle button { font-family: var(--font-mono); font-size: 11px; letter-spacing: .12em; text-transform: uppercase; padding: 9px 18px; border-radius: 999px; border: none; cursor: pointer; background: transparent; color: var(--cream-soft); transition: background .25s, color .25s; }
.toggle button.on { background: #FFFFFF; color: var(--dark); box-shadow: 0 2px 10px rgba(0, 0, 0, 0.35); }
.board { background: #111113; border: 1px solid var(--hairline-dark); border-radius: var(--radius-md); padding: clamp(14px, 2vw, 26px); }
.brow { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: clamp(14px, 2.4vw, 36px); align-items: center; padding: 14px 6px; border-top: 1px solid rgba(255, 255, 255, .07); }
.brow.head { border-top: none; padding: 2px 6px 10px; font-family: var(--font-mono); font-size: 10.5px; letter-spacing: .16em; text-transform: uppercase; color: #71717A; }
.metric { font-size: 15.5px; font-weight: 500; }
.flaps { display: inline-flex; gap: 3px; }
.flap { position: relative; display: inline-grid; place-items: center; width: 1.12em; height: 1.55em; background: linear-gradient(#27272A, #18181B); border-radius: 3px; font-family: var(--font-mono); font-size: clamp(13px, 1.4vw, 19px); line-height: 1; box-shadow: inset 0 -1px 0 rgba(0, 0, 0, .6); animation: flip .35s ease both; }
.flap::after { content: ''; position: absolute; left: 0; right: 0; top: 50%; height: 1px; background: rgba(0, 0, 0, .6); }
.flaps.hand .flap { color: #A1A1AA; }
.flaps.sd .flap { color: #FFFFFF; }
.flaps.status .flap { font-size: clamp(10px, 1vw, 13px); }
.flaps.status.hand .flap { color: #F87171; }
.flaps.status.sd .flap { color: #FAFAFA; }
@keyframes flip { from { transform: rotateX(90deg); opacity: 0; } to { transform: none; opacity: 1; } }
.note { margin-top: 26px; font-size: 10.5px; letter-spacing: .08em; color: rgba(248, 248, 246, .45); }

/* HOW */
.how { background: var(--dark); color: var(--cream); padding: clamp(64px, 9vw, 110px) 0; border-top: 1px solid var(--hairline-dark); }
.how-head { margin-bottom: 48px; }
.steps { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px; background: var(--hairline-dark); border: 1px solid var(--hairline-dark); border-radius: var(--radius-md); overflow: hidden; }
.step { background: var(--dark); padding: 32px 28px 36px; display: grid; gap: 14px; align-content: start; transition: background .25s ease; }
.step:hover { background: var(--dark-2); }
.step h3 { font-family: var(--font-serif); font-size: 1.55rem; font-weight: 500; letter-spacing: -0.02em; }
.step p { color: var(--cream-soft); font-size: 14.5px; line-height: 1.6; }

/* REPORT */
.rep-head { margin-bottom: 36px; display: grid; gap: 12px; }
.table-wrap { overflow-x: auto; background: var(--surface); }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 18px 24px; text-align: left; border-bottom: 1px solid var(--hairline); white-space: nowrap; font-size: 14.5px; }
th { font-family: var(--font-mono); font-weight: 500; font-size: 11px; letter-spacing: .12em; text-transform: uppercase; color: var(--ink-faint); background: #FCFCFA; }
tbody tr:last-child td { border-bottom: 0; }
tbody tr { transition: background .15s ease; }
tbody tr:hover { background: var(--accent-soft); }
td:first-child { font-weight: 500; }
td.neg { color: var(--danger); font-family: var(--font-mono); font-size: 13.5px; }
td.pos { color: var(--success); font-weight: 600; font-family: var(--font-mono); font-size: 13.5px; }
.quote { margin-top: 22px; padding: 16px 20px; border-left: 3px solid var(--accent); border-radius: var(--radius-sm); background: var(--surface); border-top: 1px solid var(--hairline); border-right: 1px solid var(--hairline); border-bottom: 1px solid var(--hairline); font-family: var(--font-mono); font-size: 13px; color: var(--ink-soft); }
.quote .label { display: block; margin-bottom: 6px; color: var(--accent); font-size: 10px; }

/* FAQ */
.faq { padding: 12px 40px 16px; }
.faq details { border-bottom: 1px solid var(--hairline); }
.faq details:last-child { border-bottom: 0; }
.faq summary { list-style: none; cursor: pointer; display: flex; justify-content: space-between; gap: 20px; padding: 22px 0; font-size: 1.08rem; font-weight: 500; letter-spacing: -0.01em; transition: color .15s; }
.faq summary:hover { color: var(--accent); }
.faq summary::-webkit-details-marker { display: none; }
.faq summary span { font-family: var(--font-mono); color: var(--accent); transition: transform .25s; }
.faq details[open] summary span { transform: rotate(45deg); }
.faq p { padding: 0 40px 22px 0; color: var(--ink-soft); max-width: 640px; }

/* FINAL */
.final {
  background: var(--dark);
  color: var(--cream); text-align: center; padding: clamp(80px, 11vw, 136px) 0;
}
.sm-display { font-size: clamp(2.2rem, 5vw, 3.8rem); margin-bottom: 18px; }
.final p { color: var(--cream-soft); }

.footer { background: var(--dark); border-top: 1px solid var(--hairline-dark); color: var(--cream-soft); }
.foot-in { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 28px 0 36px; }
.brand-sm { color: var(--cream); font-weight: 600; }

@media (max-width: 900px) {
  .wb-body { grid-template-columns: 1fr; }
  .wb-bridge { flex-direction: row; border-top: 1px solid var(--hairline); border-bottom: 1px solid var(--hairline); }
  .bridge-line { top: 50%; bottom: auto; left: 12%; right: 12%; width: auto; height: 1.5px; }
  .wb-source, .wb-output { border: none; }
  .two-col { grid-template-columns: 1fr; }
  .cell { padding: 28px 24px 32px; }
  .cell.side { padding: 22px 24px; flex-direction: row; align-items: center; }
  .nav-links { display: none; }
  .nav { grid-template-columns: 1fr auto; }
  .steps { grid-template-columns: repeat(2, 1fr); }
  .brow { grid-template-columns: 1fr; gap: 8px; }
  .brow.head { display: none; }
  .faq { padding: 8px 24px; }
}
@media (max-width: 540px) {
  .steps { grid-template-columns: 1fr; }
  .nav-login { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .scan-beam, .pulse-dot, .wb-live-dot, .flap { animation: none; }
}
</style>
