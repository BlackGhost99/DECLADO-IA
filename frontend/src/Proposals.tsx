// Aide au classement (COD-04 à COD-06) : recherche dans le référentiel, sans IA. Chaque piste dit
// pourquoi elle est là ; le choix reste une décision humaine motivée, liée au contrôle courant.
import { useEffect, useState } from "react";
import { api, type CodeCheck, type GoodsLine, type Proposal, type ProposalSet } from "./api";
import { errorText } from "./ui";

type Act = (a: () => Promise<unknown>) => Promise<void>;

/** Action de décision qu'implique le choix d'une proposition, selon l'état du contrôle. */
export function actionFor(check: CodeCheck, proposal: Pick<Proposal, "code">): "classify" | "complete" | "replace" {
  if (check.recognition_status === "missing" || check.recognition_status === "ambiguous") return "classify";
  if (check.recognition_status === "incomplete" && check.normalized_code && proposal.code.startsWith(check.normalized_code))
    return "complete";
  return "replace";
}

const ACTION_LABELS = { classify: "Classer sous ce code", complete: "Compléter avec ce code", replace: "Remplacer par ce code" };

export function ProposalsPanel({ goods, editionId, editable, act }: { goods: GoodsLine; editionId: string; editable: boolean; act: Act }) {
  const check = goods.latest_check;
  const [set, setSet] = useState<ProposalSet | null>(null);
  const [query, setQuery] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const recognized = check?.recognition_status === "recognized";

  useEffect(() => {
    api.proposals(goods.id).then(
      (r) => setSet(r.results[0] ?? null),
      () => setSet(null),
    );
  }, [goods.id, goods.row_version]);

  async function ask(explicit: boolean) {
    setError(null);
    try {
      setSet(await api.propose(goods.id, { edition_id: editionId || undefined, query, explicit }));
    } catch (err) {
      setError(errorText(err, "Recherche impossible."));
    }
  }

  function choose(p: Proposal) {
    if (!check) return;
    void act(() =>
      api.decide(goods.id, {
        action: actionFor(check, p),
        code_check_id: check.id,
        node_id: p.node_id,
        proposal_id: p.id,
        reason,
        goods_line_version: goods.row_version,
      }),
    );
  }

  const usable = Boolean(editable && check?.is_current && set?.is_current && set.edition_id === check?.target_edition_id);

  return (
    <div className="evidence small" aria-label="Aide au classement">
      {editable && (
        <div className="row">
          <label>
            Termes de recherche
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={goods.description} size={30} />
          </label>
          {recognized ? (
            <button type="button" onClick={() => void ask(true)}>Chercher d'autres pistes</button>
          ) : (
            <button type="button" onClick={() => void ask(false)}>Proposer des codes</button>
          )}
        </div>
      )}
      {error && <p role="alert" className="error">⚠ {error}</p>}
      {set && (
        <>
          <p className="muted">
            {set.proposals.length} piste(s) dans « {set.edition_label} » · {set.producer} · {set.is_ai ? "IA" : "sans IA"}.
            Une piste n'est pas un classement : vérifier les notes et les libellés voisins.
            {!set.is_current && " La marchandise a changé depuis : relancer la recherche."}
          </p>
          {set.questions.length > 0 && (
            <ul>
              {set.questions.map((q) => (
                <li key={q}>? {q}</li>
              ))}
            </ul>
          )}
          {set.proposals.length > 0 && (
            <ol className="proposals">
              {set.proposals.map((p) => (
                <li key={p.id}>
                  <span className="code">{p.code_display || p.code}</span> {p.label}
                  <div className="muted">{p.full_path}</div>
                  <ul>
                    {p.reasons.map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                    {p.notes.map((n) => (
                      <li key={n.id}>
                        {n.scope} {n.heading && `· ${n.heading}`} : {n.excerpt}
                        {n.mentions_exclusion && <strong> (exclusions mentionnées)</strong>}
                      </li>
                    ))}
                    {p.distinguishing.length > 0 && (
                      <li>À distinguer de : {p.distinguishing.map((d) => `${d.code_display || d.code} ${d.label}`).join(" ; ")}</li>
                    )}
                  </ul>
                  {usable && check && (
                    <button type="button" disabled={!reason.trim()} onClick={() => choose(p)}>
                      {ACTION_LABELS[actionFor(check, p)]}
                    </button>
                  )}
                </li>
              ))}
            </ol>
          )}
          {usable && set.proposals.length > 0 && (
            <label>
              Motif du choix (obligatoire)
              <input value={reason} onChange={(e) => setReason(e.target.value)} size={40} />
            </label>
          )}
          {editable && set.proposals.length > 0 && !usable && (
            <p className="muted">Contrôler le code présent contre la même édition avant de retenir une piste.</p>
          )}
        </>
      )}
    </div>
  );
}
