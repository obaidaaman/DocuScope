<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const scrolled = ref(false)
const onScroll = () => { scrolled.value = window.scrollY > 40 }

let observer
onMounted(() => {
  window.addEventListener('scroll', onScroll, { passive: true })
  observer = new IntersectionObserver(
    (entries) => entries.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('in'); observer.unobserve(e.target) } }),
    { threshold: 0.12 }
  )
  document.querySelectorAll('.reveal').forEach((el) => observer.observe(el))
})
onUnmounted(() => {
  window.removeEventListener('scroll', onScroll)
  observer?.disconnect()
})

const mode = ref('hand')
const board = [
  { metric: 'Documents compared', hand: ['SAMPLED', 'PARTIAL'], sd: ['ALL', 'CROSS-LINKED'] },
  { metric: 'Claims with a source', hand: ['SOME', 'MISSING'], sd: ['EVERY', 'CLAIM CITED'] },
  { metric: 'Conflicts found', hand: ['WHAT WAS', 'NOTICED'], sd: ['CLUSTERED', 'BY TOPIC'] },
  { metric: 'Clean corpus result', hand: ['UNCLEAR', 'UNCLEAR'], sd: ['NO FINDINGS', 'REPORTED'] },
]
const flaps = (txt) => txt.padEnd(12, ' ').split('')
const rows = computed(() => board.map((r) => ({ metric: r.metric, value: r[mode.value][0], status: r[mode.value][1] })))

const steps = [
  { n: '01', title: 'Ingest', text: 'Upload related PDFs. Each is parsed into text, tables and images, summarised where needed, and embedded for semantic search.' },
  { n: '02', title: 'Group', text: 'Passages that discuss the same thing across documents are linked into topic clusters, so rates are compared with rates.' },
  { n: '03', title: 'Judge', text: 'Each cluster goes to an LLM judge that returns CONFLICT or AGREEMENT, a severity, and verbatim quotes with page numbers.' },
  { n: '04', title: 'Decide', text: 'Conflicts wait in a review queue. Your analyst approves a source, rejects it, or writes a resolution. Agreements commit on their own.' },
]

const pillars = [
  { n: '01', label: 'Problem', title: 'Documents drift. Nobody notices until it costs money.', text: 'An amendment changes a rate, an invoice ignores it, a baseline still says the old thing. Finding that by hand means reading every page against every other page.', list: ['Amendments silently supersede clauses', 'Invoices contradict agreed terms', 'Reviewers sample instead of read'] },
  { n: '02', label: 'Solution', title: 'Compare everything. Cite everything.', text: 'SuperDocs links related passages across the whole set, asks a judge to compare them, and keeps the exact quote and page behind every statement.', list: ['Multi-document topic clustering', 'Severity-scored conflicts', 'Human sign-off before anything is committed'] },
  { n: '03', label: 'Impact', title: 'One deliverable you can defend.', text: 'Resolved conflicts and agreed clauses combine into a single register. If the corpus is clean, you get an honest report of no findings.', list: ['Audit-ready source trail', 'Faster review cycles', 'No invented problems'] },
]

const faqs = [
  { q: 'What is SuperDocs?', a: 'SuperDocs is a document reconciliation platform. It ingests related documents, finds where they disagree, and produces one grounded report where every claim points to the page and quote it came from.' },
  { q: 'How many documents can I compare?', a: 'From two upwards. Related passages are linked across the entire set, so a clause in one document can be compared with the matching clauses in all the others at once.' },
  { q: 'Does it replace our reviewers?', a: 'No. The system does the reading and comparing. Conflicts go to a review queue and your team approves, rejects or rewrites each one.' },
  { q: 'What file types are supported?', a: 'PDF today. The extraction pipeline handles text, tables and images inside those PDFs.' },
  { q: 'What if the documents all agree?', a: 'You get a report of no findings, with the agreed clauses and their citations. Nothing is manufactured to look busy.' },
]
</script>

<template>
  <div class="landing">
    <header class="nav" :class="{ scrolled }">
      <RouterLink to="/" class="brand" id="nav-brand" aria-label="SuperDocs home">
        <svg width="26" height="26" viewBox="0 0 26 26" fill="none" aria-hidden="true">
          <rect x="3" y="2" width="14" height="18" rx="1.5" stroke="#F0EBE1" stroke-width="1.5"/>
          <rect x="9" y="6" width="14" height="18" rx="1.5" fill="#14130F" stroke="#C2A45C" stroke-width="1.5"/>
          <path d="M12.5 12h7M12.5 15.5h7M12.5 19h4" stroke="#F0EBE1" stroke-width="1.3" stroke-linecap="round"/>
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
        <RouterLink to="/login" class="nav-login" id="nav-login">Log in</RouterLink>
        <RouterLink to="/signup" class="btn btn-cream sm" id="nav-signup">Get started</RouterLink>
      </div>
    </header>

    <main>
      <!-- HERO -->
      <section class="hero">
        <div class="container hero-in">
          <div class="reveal">
            <h1 class="display">Document Reconciliation</h1>
            <div class="tagline">
              <span></span><p class="label">Every claim traced, not just summarised</p><span></span>
            </div>
          </div>
          <p class="body-lg hero-sub reveal">
            SuperDocs reads a pile of related contracts, finds exactly where they disagree,
            and hands you one grounded report. Your team signs every call.
          </p>
          <div class="hero-cta reveal">
            <RouterLink to="/signup" class="btn btn-cream" id="hero-signup">Get started</RouterLink>
            <a href="#how" class="btn btn-outline-dark" id="hero-how">How it works</a>
          </div>

          <div class="planes" aria-hidden="true">
            <div class="plane plane-a"><i v-for="w in [92,78,86,64,90,71,83]" :key="w" :style="{ width: w + '%' }"></i></div>
            <div class="plane plane-b"><i v-for="w in [92,78,86,64,90,71,83]" :key="w" :style="{ width: w + '%' }"></i></div>
            <div class="plane plane-c">
              <div class="plane-top">
                <span class="label muted">Reconciliation</span>
                <span class="label chip">3 docs · 2 topics</span>
              </div>
              <div class="plane-row bad"><span>Senior Engineer Rate</span><b>$120 / $135 / $150</b></div>
              <div class="plane-row bad"><span>Payment Terms</span><b>Net 45 / Net 30</b></div>
              <div class="plane-row ok"><span>Uptime SLA</span><b>99.9% agreed</b></div>
              <div class="tags">
                <span>Ingest ✓</span><span>Cluster ✓</span><span>Judge ✓</span><span>Review</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- WHAT IS -->
      <section id="what" class="band">
        <div class="container">
          <div class="frame two-col reveal">
            <div class="cell side"><h2 class="label faint">What is SuperDocs?</h2></div>
            <div class="cell">
              <p class="what-text">
                SuperDocs is a document reconciliation platform for teams that manage contracts, amendments and invoices.
                It understands the pile, finds the disagreements, and produces one deliverable where every claim
                traces to its source. Clean corpora resolve straight through, conflicts get a reviewer, and your team keeps the decisions.
              </p>
              <div class="links">
                <a href="#how">Document ingestion</a>
                <a href="#how">Conflict detection</a>
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
              <span class="label gold">Status board</span>
              <h2 class="h2 on-dark">Same documents. Different board.</h2>
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
              <span class="flaps" :class="mode"><span v-for="(c, i) in flaps(r.value)" :key="mode + i" class="flap" :style="{ animationDelay: i * 25 + 'ms' }">{{ c }}</span></span>
              <span class="flaps status" :class="mode"><span v-for="(c, i) in flaps(r.status)" :key="mode + i" class="flap" :style="{ animationDelay: i * 25 + 'ms' }">{{ c }}</span></span>
            </div>
          </div>
          <p class="label note">Illustrative comparison of manual review versus the SuperDocs workflow.</p>
        </div>
      </section>

      <!-- MANIFESTO -->
      <section class="band">
        <div class="container">
          <div class="frame two-col reveal">
            <div class="cell side"><span class="label faint">Our belief</span></div>
            <div class="cell">
              <p class="h3 manifesto">A contract is a promise. Reconciliation is where you find out whether every document <span class="serif-accent">agrees</span> - or <span class="serif-accent">doesn't</span>.</p>
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
              <span class="label">{{ p.label }}</span>
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
            <span class="label gold">How it works</span>
            <h2 class="h2 on-dark">From a pile of PDFs to <span class="serif-accent">one answer</span></h2>
          </div>
          <div class="steps">
            <article v-for="s in steps" :key="s.n" class="step reveal">
              <span class="label gold">{{ s.n }}</span>
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
            <span class="label faint">Sample deliverable</span>
            <h2 class="h2">A register where every row is <span class="serif-accent">sourced</span></h2>
          </div>
          <div class="frame table-wrap reveal">
            <table>
              <thead>
                <tr><th>Clause</th><th>Baseline</th><th>Amendment</th><th>Invoice</th><th>Committed</th></tr>
              </thead>
              <tbody>
                <tr><td>Senior Engineer Rate</td><td>$120 / hr</td><td>$135 / hr</td><td class="neg">$150 / hr</td><td class="pos">$135 / hr</td></tr>
                <tr><td>Payment Terms</td><td>Net 45</td><td>Net 30</td><td>Net 30</td><td class="pos">Net 30</td></tr>
                <tr><td>Travel Expenses</td><td>$0</td><td>Unchanged</td><td class="neg">$3,200</td><td class="pos">$0</td></tr>
                <tr><td>Uptime SLA</td><td>99.9%</td><td>99.9%</td><td>n/a</td><td class="pos">99.9%</td></tr>
              </tbody>
            </table>
          </div>
          <blockquote class="quote reveal">
            <span class="label">Doc 3 · Page 1 · flagged</span>
            “160 Hours @ $150 USD / hour $24,000 USD”
          </blockquote>
        </div>
      </section>

      <!-- FAQ -->
      <section id="faq" class="band tight">
        <div class="container">
          <div class="frame two-col reveal">
            <div class="cell side"><h2 class="label faint">Questions</h2></div>
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
          <h2 class="display sm-display">Stop hunting for <span class="serif-accent">contradictions.</span></h2>
          <p class="body-lg">Create an account and run your first reconciliation.</p>
          <div class="hero-cta center">
            <RouterLink to="/signup" class="btn btn-cream" id="cta-signup">Get started</RouterLink>
            <RouterLink to="/login" class="btn btn-outline-dark" id="cta-login">Log in</RouterLink>
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
.nav { position: fixed; inset: 0 0 auto 0; z-index: 50; height: 68px; display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; padding: 0 clamp(20px, 3vw, 44px); border-bottom: 1px solid transparent; transition: background .25s, border-color .25s; }
.nav.scrolled { background: rgba(20, 19, 15, .88); backdrop-filter: blur(12px); border-color: var(--hairline-dark); }
.brand { display: inline-flex; align-items: center; gap: 9px; color: var(--cream); font-size: 18px; font-weight: 500; letter-spacing: -0.01em; }
.nav-links { display: flex; gap: 2px; }
.nav-links a { padding: 6px 13px; font-size: 15px; color: var(--cream-soft); transition: color .15s; }
.nav-links a:hover { color: var(--cream); }
.nav-auth { display: flex; align-items: center; justify-content: flex-end; gap: 18px; }
.nav-login { color: var(--cream-soft); font-size: 15px; transition: color .15s; }
.nav-login:hover { color: var(--cream); }
.btn.sm { padding: 10px 20px; font-size: 14px; }

/* HERO */
.hero { background: linear-gradient(180deg, #14130F 0%, #1E1D16 42%, #2E2D24 68%, #55523F 86%, var(--paper) 100%); padding-top: clamp(130px, 11vw, 160px); overflow: hidden; }
.hero-in { text-align: center; }
.hero h1 { color: var(--cream); max-width: 1000px; margin: 0 auto; }
.tagline { display: flex; align-items: center; justify-content: center; gap: 18px; margin-top: 22px; }
.tagline span { height: 1px; width: clamp(28px, 6vw, 72px); background: rgba(194, 164, 92, .45); }
.tagline p { color: var(--gold); letter-spacing: .18em; }
.hero-sub { color: var(--cream-soft); max-width: 640px; margin: 26px auto 0; text-wrap: balance; }
.hero-cta { display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; margin-top: 36px; }

.planes { position: relative; width: min(560px, 86vw); height: 360px; margin: clamp(44px, 8vw, 72px) auto 0; }
.plane { position: absolute; width: min(400px, 74vw); padding: 26px 28px 30px; border: 1px solid var(--hairline); border-radius: 2px; box-shadow: 0 24px 60px rgba(10, 9, 6, .35); text-align: left; animation: float 9s ease-in-out infinite; display: grid; gap: 9px; align-content: start; }
.plane i { display: block; height: 7px; background: var(--hairline); border-radius: 1px; }
.plane-a { left: 40px; top: 20px; background: #DDD7CB; transform: rotate(-7deg); }
.plane-b { left: 120px; top: 10px; background: var(--paper-deep); transform: rotate(5deg); animation-delay: -3s; }
.plane-c { left: 80px; top: 0; background: var(--paper); transform: rotate(-1.5deg); animation-delay: -6s; gap: 12px; }
@keyframes float { 0%, 100% { margin-top: 0; } 50% { margin-top: -8px; } }
.plane-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.muted { color: var(--ink-faint); }
.chip { background: var(--olive); color: var(--paper); padding: 5px 10px; border-radius: 2px; font-size: 10px; }
.plane-row { display: flex; justify-content: space-between; gap: 12px; padding: 10px 12px; border-left: 2px solid; background: rgba(26, 25, 23, .04); font-size: 13px; }
.plane-row b { font-family: var(--font-mono); font-weight: 500; font-size: 11.5px; }
.plane-row.bad { border-color: #B5532A; }
.plane-row.ok { border-color: #5E7A4A; }
.tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
.tags span { font-family: var(--font-mono); font-size: 10px; letter-spacing: .06em; text-transform: uppercase; color: var(--ink-faint); border: 1px solid var(--hairline); border-radius: 2px; padding: 3px 7px; }

/* BANDS / FRAMES */
.band { padding: clamp(48px, 7vw, 80px) 0; }
.band.tight { padding-top: 0; }
.two-col { display: grid; grid-template-columns: 280px 1fr; gap: 1px; background: var(--hairline); }
.cell { background: var(--paper); padding: 36px 40px 40px; }
.cell.side { padding: 36px 32px; display: flex; flex-direction: column; gap: 14px; align-items: flex-start; }
.faint { color: var(--ink-faint); font-weight: 500; }
.what-text { font-size: 18.5px; line-height: 1.6; letter-spacing: -0.01em; max-width: 700px; }
.links { display: flex; flex-wrap: wrap; gap: 10px 18px; margin-top: 22px; }
.links a, .underline { font-size: 14px; border-bottom: 1px solid var(--hairline-strong); padding-bottom: 2px; transition: border-color .2s; }
.links a:hover, .underline:hover { border-color: var(--ink); }
.underline { display: inline-block; margin-top: 28px; font-size: 15px; }
.manifesto { max-width: 720px; }
.pillar { margin-bottom: 20px; }
.pillar .cell:not(.side) { display: grid; gap: 18px; }
.pillar .h2 { max-width: 560px; }
.soft { color: var(--ink-soft); max-width: 520px; }
.tag-n { padding: 5px 8px; border-radius: 2px; background: var(--ink); color: var(--cream); }
.list { list-style: none; display: grid; gap: 8px; }
.list li { padding-left: 22px; position: relative; font-size: 15px; }
.list li::before { content: ''; position: absolute; left: 0; top: .6em; width: 10px; height: 1px; background: var(--ink); }

/* BOARD */
.board-sec { background: var(--dark); color: var(--cream); padding: clamp(64px, 9vw, 116px) 0; }
.board-top { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: 22px; margin-bottom: clamp(28px, 4vw, 48px); }
.on-dark { color: var(--cream); margin-top: 14px; max-width: 640px; }
.gold { color: var(--gold); }
.toggle { display: inline-flex; padding: 4px; border-radius: 999px; border: 1px solid var(--hairline-dark); background: rgba(240, 235, 225, .04); }
.toggle button { font-family: var(--font-mono); font-size: 11px; letter-spacing: .12em; text-transform: uppercase; padding: 9px 16px; border-radius: 999px; border: none; cursor: pointer; background: transparent; color: var(--cream-soft); transition: background .25s, color .25s; }
.toggle button.on { background: var(--gold); color: var(--dark); }
.board { background: #0D0C09; border: 1px solid var(--hairline-dark); border-radius: 10px; padding: clamp(14px, 2vw, 26px); }
.brow { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: clamp(14px, 2.4vw, 36px); align-items: center; padding: 14px 6px; border-top: 1px solid rgba(240, 235, 225, .07); }
.brow.head { border-top: none; padding: 2px 6px 10px; font-family: var(--font-mono); font-size: 10.5px; letter-spacing: .16em; text-transform: uppercase; color: rgba(240, 235, 225, .4); }
.metric { font-size: 16px; font-weight: 500; }
.flaps { display: inline-flex; gap: 3px; }
.flap { position: relative; display: inline-grid; place-items: center; width: 1.12em; height: 1.55em; background: linear-gradient(#24231C, #1A1914); border-radius: 3px; font-family: var(--font-mono); font-size: clamp(13px, 1.4vw, 20px); line-height: 1; box-shadow: inset 0 -1px 0 rgba(0, 0, 0, .6); animation: flip .35s ease both; }
.flap::after { content: ''; position: absolute; left: 0; right: 0; top: 50%; height: 1px; background: rgba(0, 0, 0, .65); }
.flaps.hand .flap { color: rgba(240, 235, 225, .6); }
.flaps.sd .flap { color: var(--cream); }
.flaps.status .flap { font-size: clamp(10px, 1vw, 13px); }
.flaps.status.hand .flap { color: var(--copper); }
.flaps.status.sd .flap { color: var(--gold); }
@keyframes flip { from { transform: rotateX(90deg); opacity: 0; } to { transform: none; opacity: 1; } }
.note { margin-top: 28px; font-size: 10.5px; letter-spacing: .08em; color: rgba(240, 235, 225, .42); }

/* HOW */
.how { background: var(--dark); color: var(--cream); padding: 0 0 clamp(64px, 9vw, 110px); border-top: 1px solid var(--hairline-dark); padding-top: clamp(64px, 9vw, 110px); }
.how-head { margin-bottom: 48px; }
.steps { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px; background: var(--hairline-dark); border: 1px solid var(--hairline-dark); }
.step { background: var(--dark); padding: 32px 28px 36px; display: grid; gap: 14px; align-content: start; transition: background .25s; }
.step:hover { background: var(--dark-2); }
.step h3 { font-size: 1.5rem; font-weight: 500; letter-spacing: -0.02em; }
.step p { color: var(--cream-soft); font-size: 15px; }

/* REPORT */
.rep-head { margin-bottom: 36px; display: grid; gap: 14px; }
.table-wrap { overflow-x: auto; background: var(--paper); }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 18px 24px; text-align: left; border-bottom: 1px solid var(--hairline); white-space: nowrap; font-size: 15px; }
th { font-family: var(--font-mono); font-weight: 500; font-size: 11px; letter-spacing: .14em; text-transform: uppercase; color: var(--ink-faint); }
tbody tr:last-child td { border-bottom: 0; }
td:first-child { font-weight: 500; }
td.neg { color: #B5532A; }
td.pos { color: #4D6B3A; font-weight: 500; }
.quote { margin-top: 24px; padding: 16px 20px; border-left: 2px solid var(--ink); background: rgba(26, 25, 23, .04); font-family: var(--font-mono); font-size: 13px; color: var(--ink-soft); }
.quote .label { display: block; margin-bottom: 6px; color: #B5532A; font-size: 10px; }

/* FAQ */
.faq { padding: 12px 40px 16px; }
.faq details { border-bottom: 1px solid var(--hairline); }
.faq details:last-child { border-bottom: 0; }
.faq summary { list-style: none; cursor: pointer; display: flex; justify-content: space-between; gap: 20px; padding: 22px 0; font-size: 1.1rem; font-weight: 500; letter-spacing: -0.01em; }
.faq summary::-webkit-details-marker { display: none; }
.faq summary span { font-family: var(--font-mono); transition: transform .25s; }
.faq details[open] summary span { transform: rotate(45deg); }
.faq p { padding: 0 40px 22px 0; color: var(--ink-soft); max-width: 640px; }

/* FINAL */
.final { background: var(--dark); color: var(--cream); text-align: center; padding: clamp(80px, 11vw, 140px) 0; }
.sm-display { font-size: clamp(2.2rem, 5vw, 4rem); margin-bottom: 20px; }
.final p { color: var(--cream-soft); }

.footer { background: var(--dark); border-top: 1px solid var(--hairline-dark); color: var(--cream-soft); }
.foot-in { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 28px 0 36px; }
.brand-sm { color: var(--cream); font-weight: 500; }

@media (max-width: 900px) {
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
@media (max-width: 560px) {
  .steps { grid-template-columns: 1fr; }
  .nav-login { display: none; }
  .foot-in { flex-direction: column; text-align: center; }
  .planes { height: 380px; }
}
@media (prefers-reduced-motion: reduce) {
  .plane, .flap { animation: none; }
}
</style>
