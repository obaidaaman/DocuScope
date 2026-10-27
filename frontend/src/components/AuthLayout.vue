<template>
  <div class="auth">
    <aside class="art">
      <RouterLink to="/" class="brand" aria-label="SuperDocs home">
        <svg width="26" height="26" viewBox="0 0 26 26" fill="none" aria-hidden="true">
          <rect x="3" y="2" width="14" height="18" rx="1.5" stroke="#F0EBE1" stroke-width="1.5"/>
          <rect x="9" y="6" width="14" height="18" rx="1.5" fill="#14130F" stroke="#C2A45C" stroke-width="1.5"/>
          <path d="M12.5 12h7M12.5 15.5h7M12.5 19h4" stroke="#F0EBE1" stroke-width="1.3" stroke-linecap="round"/>
        </svg>
        <span>SuperDocs</span>
      </RouterLink>

      <div class="art-body">
        <p class="label gold">Document reconciliation</p>
        <h2>Every claim <span class="serif-accent">traced</span> to its source.</h2>
        <div class="planes" aria-hidden="true">
          <div class="plane pa"></div>
          <div class="plane pb"></div>
          <div class="plane pc">
            <span class="label muted">Finding</span>
            <div class="row bad"><span>Senior Engineer Rate</span><b>$120 / $135 / $150</b></div>
            <div class="quote">Doc 3 · p.1 “160 Hours @ $150 USD / hour”</div>
          </div>
        </div>
      </div>
      <small>© {{ new Date().getFullYear() }} SuperDocs</small>
    </aside>

    <main class="panel">
      <slot />
    </main>
  </div>
</template>

<style scoped>
.auth { display: grid; grid-template-columns: minmax(380px, 1fr) minmax(420px, 1fr); min-height: 100vh; }

.art { background: linear-gradient(170deg, #14130F 0%, #1E1D16 50%, #2E2D24 100%); color: var(--cream); padding: 32px clamp(28px, 4vw, 56px); display: flex; flex-direction: column; justify-content: space-between; position: relative; overflow: hidden; }
.brand { display: inline-flex; align-items: center; gap: 9px; font-size: 18px; font-weight: 500; letter-spacing: -0.01em; }
.art-body { display: grid; gap: 18px; }
.art h2 { font-size: clamp(2rem, 3.4vw, 3rem); font-weight: 500; letter-spacing: -0.03em; line-height: 1.08; max-width: 420px; }
.gold { color: var(--gold); }
.art small { color: var(--cream-soft); }

.planes { position: relative; height: 230px; margin-top: 18px; max-width: 380px; }
.plane { position: absolute; width: 300px; border: 1px solid var(--hairline); border-radius: 2px; box-shadow: 0 24px 60px rgba(10, 9, 6, .4); animation: float 9s ease-in-out infinite; }
.pa { left: 10px; top: 24px; height: 170px; background: #DDD7CB; transform: rotate(-7deg); }
.pb { left: 52px; top: 14px; height: 170px; background: var(--paper-deep); transform: rotate(5deg); animation-delay: -3s; }
.pc { left: 30px; top: 0; padding: 20px 22px; background: var(--paper); color: var(--ink); transform: rotate(-1.5deg); animation-delay: -6s; display: grid; gap: 12px; }
@keyframes float { 0%, 100% { margin-top: 0; } 50% { margin-top: -8px; } }
.muted { color: var(--ink-faint); }
.row { display: flex; justify-content: space-between; gap: 10px; padding: 10px 12px; border-left: 2px solid #B5532A; background: rgba(26, 25, 23, .04); font-size: 12.5px; }
.row b { font-family: var(--font-mono); font-weight: 500; font-size: 11px; }
.quote { font-family: var(--font-mono); font-size: 11px; color: var(--ink-soft); }

.panel { background: var(--paper); display: grid; place-items: center; padding: 48px clamp(24px, 5vw, 72px); }

@media (max-width: 860px) {
  .auth { grid-template-columns: 1fr; }
  .art { display: none; }
  .panel { min-height: 100vh; }
}
@media (prefers-reduced-motion: reduce) { .plane { animation: none; } }
</style>
