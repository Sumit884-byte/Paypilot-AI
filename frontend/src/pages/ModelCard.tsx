import { useEffect, useState } from 'react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { GlassCard } from '../components/ui/GlassCard'
import { Button } from '../components/ui/Button'
import { MetricCard, Notice, PageHeading, Icon } from '../components/ui/Workspace'
import { apiRequest } from '../lib/api'

type MetricAvailability = Record<string, 'available' | 'not_yet_evaluated' | string>

type ModelCardPayload = {
  status: string
  model_name: string
  model_version: string
  model_type: string
  model_purpose: string
  is_trained_model: boolean
  evaluation_dataset: null | {
    kind?: string
    note?: string
    n_rows?: number
    seed?: number
    split?: string
    test_n?: number
    positive_rate_test?: number
  }
  last_evaluation_date: string | null
  metrics: {
    auc_roc: number | null
    precision: number | null
    recall: number | null
    f1_score: number | null
    accuracy: number | null
    pr_auc: number | null
    log_loss: number | null
    brier: number | null
    ks: number | null
  }
  metric_availability: MetricAvailability
  calibration_status: string
  feature_names: string[]
  feature_importance_gain: Record<string, number>
  baseline_logistic_regression_test?: { roc_auc?: number; pr_auc?: number; brier?: number; ks?: number } | null
  caveat?: string
  decision_support_statement: string
  fairness: {
    sensitive_attributes_excluded: string[]
    sensitive_or_proxy_features_used: string[]
    features_used: string[]
    top_features_by_gain: Array<{ feature: string; gain: number }>
    bias_considerations: string[]
    data_quality_limitations: string[]
  }
  limitations: string[]
  human_review_requirements: string[]
  explainability: { method: string; detail: string }
}

type EvaluationPayload = {
  status: string
  detail?: string
  threshold?: number
  roc_curve: null | { points: Array<{ fpr: number; tpr: number }>; diagonal: Array<{ fpr: number; tpr: number }> }
  calibration_curve: null | {
    points: Array<{ mean_predicted: number; fraction_positives: number }>
    perfect: Array<{ mean_predicted: number; fraction_positives: number }>
    note?: string
  }
  confusion_matrix: null | {
    matrix: number[][]
    true_negative: number
    false_positive: number
    false_negative: number
    true_positive: number
    threshold: number
  }
  threshold_metrics: null | {
    precision: number
    recall: number
    f1_score: number
    accuracy: number
    note?: string
  }
  metrics_comparison: null | Array<Record<string, string | number | null | undefined>>
  computed_at_utc?: string | null
}

function metricDisplay(value: number | null | undefined, availability?: string) {
  if (availability === 'not_yet_evaluated' || value === null || value === undefined) {
    return 'Not yet evaluated'
  }
  return typeof value === 'number' ? value.toFixed(4) : 'Not yet evaluated'
}

export function ModelCard() {
  const [card, setCard] = useState<ModelCardPayload | null>(null)
  const [evaluation, setEvaluation] = useState<EvaluationPayload | null>(null)
  const [error, setError] = useState('')
  const [evalError, setEvalError] = useState('')
  const [loadingEval, setLoadingEval] = useState(false)

  useEffect(() => {
    apiRequest<ModelCardPayload>('/model-card')
      .then(setCard)
      .catch((e) => setError(e instanceof Error ? e.message : 'Could not load model card'))
  }, [])

  async function loadEvaluation() {
    setLoadingEval(true)
    setEvalError('')
    try {
      const result = await apiRequest<EvaluationPayload>('/model-card/evaluation?threshold=0.5')
      setEvaluation(result)
    } catch (e) {
      setEvalError(e instanceof Error ? e.message : 'Could not compute evaluation curves')
    } finally {
      setLoadingEval(false)
    }
  }

  const thresholdMetrics = evaluation?.threshold_metrics
  const comparisonBars = (evaluation?.metrics_comparison || [])
    .filter((row) => typeof row.roc_auc === 'number')
    .map((row) => ({
      name: String(row.label).replace(' (stored test)', '').replace('LightGBM', 'LGBM'),
      roc_auc: Number(row.roc_auc),
      pr_auc: typeof row.pr_auc === 'number' ? Number(row.pr_auc) : undefined,
    }))

  const confusionData = evaluation?.confusion_matrix
    ? [
        { cell: 'TN', value: evaluation.confusion_matrix.true_negative },
        { cell: 'FP', value: evaluation.confusion_matrix.false_positive },
        { cell: 'FN', value: evaluation.confusion_matrix.false_negative },
        { cell: 'TP', value: evaluation.confusion_matrix.true_positive },
      ]
    : []

  return (
    <div className="space-y-6">
      <PageHeading
        eyebrow="Model card"
        title="How PayScore is evaluated."
        detail="Committed synthetic-split metrics and responsible-AI disclosures. No placeholder performance numbers."
        action={
          <Button onClick={loadEvaluation} disabled={loadingEval}>
            {loadingEval ? 'Computing curves…' : 'Load evaluation charts'}
          </Button>
        }
      />

      <Notice>
        {card?.decision_support_statement
          || 'PayScore provides decision-support insights, not guaranteed credit approval or financial outcomes.'}
      </Notice>
      {error && <Notice tone="warning">{error}</Notice>}
      {card?.caveat && <Notice tone="warning">{card.caveat}</Notice>}

      {card && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="Model"
              value={card.model_name}
              detail={`${card.model_type} · ${card.model_version}`}
              icon={<Icon name="spark" />}
              delay={0.05}
            />
            <MetricCard
              label="AUC-ROC (test)"
              value={metricDisplay(card.metrics.auc_roc, card.metric_availability.auc_roc)}
              detail={card.is_trained_model ? 'Synthetic test split' : 'No trained model'}
              icon={<Icon name="trend" />}
              tone="gold"
              delay={0.1}
            />
            <MetricCard
              label="Precision"
              value={metricDisplay(
                thresholdMetrics?.precision ?? card.metrics.precision,
                thresholdMetrics ? 'available' : card.metric_availability.precision,
              )}
              detail={thresholdMetrics ? 'At PD threshold 0.5 (recomputed)' : 'Load evaluation charts to compute'}
              icon={<Icon name="check" />}
              tone="green"
              delay={0.15}
            />
            <MetricCard
              label="Calibration"
              value={card.calibration_status.startsWith('Not') ? 'Not yet evaluated' : 'See notes'}
              detail={card.calibration_status}
              icon={<Icon name="shield" />}
              tone="rose"
              delay={0.2}
            />
          </div>

          <div className="grid gap-5 xl:grid-cols-2">
            <GlassCard>
              <h2 className="font-semibold">Model performance summary</h2>
              <p className="mt-1 text-xs text-slate-500">{card.model_purpose}</p>
              <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                {[
                  ['Recall', metricDisplay(thresholdMetrics?.recall ?? card.metrics.recall, thresholdMetrics ? 'available' : card.metric_availability.recall)],
                  ['F1 score', metricDisplay(thresholdMetrics?.f1_score ?? card.metrics.f1_score, thresholdMetrics ? 'available' : card.metric_availability.f1_score)],
                  ['Accuracy', metricDisplay(thresholdMetrics?.accuracy ?? card.metrics.accuracy, thresholdMetrics ? 'available' : card.metric_availability.accuracy)],
                  ['PR-AUC', metricDisplay(card.metrics.pr_auc, card.metric_availability.pr_auc)],
                  ['Log loss', metricDisplay(card.metrics.log_loss, card.metric_availability.log_loss)],
                  ['Brier', metricDisplay(card.metrics.brier, card.metric_availability.brier)],
                  ['KS', metricDisplay(card.metrics.ks, card.metric_availability.ks)],
                  ['Last evaluation', card.last_evaluation_date || 'Not yet evaluated'],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-xl border border-[rgb(var(--line))] px-3 py-2">
                    <dt className="text-[11px] uppercase tracking-wide text-slate-500">{label}</dt>
                    <dd className="mt-1 font-medium">{value}</dd>
                  </div>
                ))}
              </dl>
            </GlassCard>

            <GlassCard>
              <h2 className="font-semibold">Evaluation metadata</h2>
              {card.evaluation_dataset ? (
                <dl className="mt-4 space-y-2 text-sm">
                  <div className="flex justify-between gap-3"><dt className="text-slate-500">Dataset</dt><dd>{card.evaluation_dataset.kind}</dd></div>
                  <div className="flex justify-between gap-3"><dt className="text-slate-500">Rows</dt><dd>{card.evaluation_dataset.n_rows ?? '—'}</dd></div>
                  <div className="flex justify-between gap-3"><dt className="text-slate-500">Test n</dt><dd>{card.evaluation_dataset.test_n ?? '—'}</dd></div>
                  <div className="flex justify-between gap-3"><dt className="text-slate-500">Seed</dt><dd>{card.evaluation_dataset.seed ?? '—'}</dd></div>
                  <div className="flex justify-between gap-3"><dt className="text-slate-500">Split</dt><dd className="text-right">{card.evaluation_dataset.split}</dd></div>
                  <p className="pt-2 text-xs leading-relaxed text-slate-500">{card.evaluation_dataset.note}</p>
                </dl>
              ) : (
                <p className="mt-4 text-sm text-slate-500">Not yet evaluated — no trained-model dataset metadata.</p>
              )}
            </GlassCard>
          </div>

          <div className="grid gap-5 xl:grid-cols-2">
            <GlassCard>
              <h2 className="font-semibold">ROC curve</h2>
              <p className="mb-4 mt-1 text-xs text-slate-500">Synthetic test split only. Not a real-world benchmark.</p>
              {evalError && <Notice tone="warning">{evalError}</Notice>}
              {evaluation?.status === 'available' && evaluation.roc_curve?.points?.length ? (
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={evaluation.roc_curve.points}>
                      <CartesianGrid strokeDasharray="3 3" opacity={0.35} />
                      <XAxis dataKey="fpr" type="number" domain={[0, 1]} tickFormatter={(v) => Number(v).toFixed(1)} label={{ value: 'False positive rate', position: 'insideBottom', offset: -2 }} />
                      <YAxis dataKey="tpr" type="number" domain={[0, 1]} tickFormatter={(v) => Number(v).toFixed(1)} label={{ value: 'True positive rate', angle: -90, position: 'insideLeft' }} />
                      <Tooltip formatter={(value) => Number(value).toFixed(4)} />
                      <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke="#94a3b8" strokeDasharray="4 4" />
                      <Area type="monotone" dataKey="tpr" name="ROC" stroke="#0070BA" fill="#0070BA33" />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <EmptyChart message={evaluation?.detail || 'Click “Load evaluation charts” to recompute the ROC from the loaded model.'} />
              )}
            </GlassCard>

            <GlassCard>
              <h2 className="font-semibold">Calibration / reliability</h2>
              <p className="mb-4 mt-1 text-xs text-slate-500">{evaluation?.calibration_curve?.note || card.calibration_status}</p>
              {evaluation?.status === 'available' && evaluation.calibration_curve?.points?.length ? (
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={evaluation.calibration_curve.points}>
                      <CartesianGrid strokeDasharray="3 3" opacity={0.35} />
                      <XAxis dataKey="mean_predicted" type="number" domain={[0, 1]} label={{ value: 'Mean predicted PD', position: 'insideBottom', offset: -2 }} />
                      <YAxis type="number" domain={[0, 1]} label={{ value: 'Fraction of defaults', angle: -90, position: 'insideLeft' }} />
                      <Tooltip formatter={(value) => Number(value).toFixed(4)} />
                      <Legend />
                      <Line type="monotone" dataKey="fraction_positives" name="Observed" stroke="#0070BA" strokeWidth={2} dot />
                      <Line type="monotone" data={evaluation.calibration_curve.perfect} dataKey="fraction_positives" name="Perfect" stroke="#94a3b8" strokeDasharray="4 4" dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <EmptyChart message="Not yet evaluated — calibration chart appears after curves are computed." />
              )}
            </GlassCard>
          </div>

          <div className="grid gap-5 xl:grid-cols-2">
            <GlassCard>
              <h2 className="font-semibold">Confusion matrix</h2>
              <p className="mb-4 mt-1 text-xs text-slate-500">
                {evaluation?.confusion_matrix
                  ? `At PD threshold ${evaluation.confusion_matrix.threshold}`
                  : 'Not yet evaluated'}
              </p>
              {confusionData.length ? (
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={confusionData}>
                      <CartesianGrid strokeDasharray="3 3" opacity={0.35} />
                      <XAxis dataKey="cell" />
                      <YAxis allowDecimals={false} />
                      <Tooltip />
                      <Bar dataKey="value" name="Count" radius={[6, 6, 0, 0]}>
                        {confusionData.map((entry) => (
                          <Cell key={entry.cell} fill={entry.cell === 'TP' || entry.cell === 'TN' ? '#0070BA' : '#F5B942'} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <EmptyChart message="Confusion matrix requires an on-demand evaluation pass." />
              )}
            </GlassCard>

            <GlassCard>
              <h2 className="font-semibold">Performance comparison</h2>
              <p className="mb-4 mt-1 text-xs text-slate-500">Stored metadata AUC vs logistic baseline (synthetic test).</p>
              {comparisonBars.length ? (
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={comparisonBars}>
                      <CartesianGrid strokeDasharray="3 3" opacity={0.35} />
                      <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                      <YAxis domain={[0.7, 1]} tickFormatter={(v) => Number(v).toFixed(2)} />
                      <Tooltip />
                      <Legend />
                      <Bar dataKey="roc_auc" name="ROC-AUC" fill="#0070BA" radius={[6, 6, 0, 0]} />
                      <Bar dataKey="pr_auc" name="PR-AUC" fill="#F5B942" radius={[6, 6, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : card.baseline_logistic_regression_test?.roc_auc != null && card.metrics.auc_roc != null ? (
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={[
                      { name: 'LightGBM', roc_auc: card.metrics.auc_roc, pr_auc: card.metrics.pr_auc },
                      { name: 'LogReg baseline', roc_auc: card.baseline_logistic_regression_test.roc_auc, pr_auc: card.baseline_logistic_regression_test.pr_auc },
                    ]}>
                      <CartesianGrid strokeDasharray="3 3" opacity={0.35} />
                      <XAxis dataKey="name" />
                      <YAxis domain={[0.7, 1]} />
                      <Tooltip />
                      <Legend />
                      <Bar dataKey="roc_auc" name="ROC-AUC" fill="#0070BA" radius={[6, 6, 0, 0]} />
                      <Bar dataKey="pr_auc" name="PR-AUC" fill="#F5B942" radius={[6, 6, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <EmptyChart message="Comparison unavailable until trained-model metadata is present." />
              )}
            </GlassCard>
          </div>

          <div className="grid gap-5 xl:grid-cols-2">
            <GlassCard>
              <h2 className="font-semibold">Fairness & responsible AI</h2>
              <div className="mt-4 space-y-4 text-sm">
                <div>
                  <p className="text-xs font-semibold uppercase text-slate-500">Sensitive attributes excluded</p>
                  <p className="mt-1 text-slate-700 dark:text-slate-200">{card.fairness.sensitive_attributes_excluded.join(', ')}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase text-slate-500">Features used by the model</p>
                  <p className="mt-1 text-xs leading-relaxed text-slate-600">{card.fairness.features_used.join(', ')}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase text-amber-700">Sensitive / proxy features used</p>
                  <p className="mt-1">{card.fairness.sensitive_or_proxy_features_used.join(', ') || 'None listed'}</p>
                </div>
                <ul className="list-disc space-y-1 pl-5 text-xs text-slate-600">
                  {card.fairness.bias_considerations.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
            </GlassCard>

            <GlassCard>
              <h2 className="font-semibold">Model limitations</h2>
              <ul className="mt-4 list-disc space-y-2 pl-5 text-sm text-slate-600">
                {card.limitations.map((item) => <li key={item}>{item}</li>)}
              </ul>
              <h3 className="mt-5 text-xs font-semibold uppercase text-slate-500">Data quality</h3>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-slate-600">
                {card.fairness.data_quality_limitations.map((item) => <li key={item}>{item}</li>)}
              </ul>
              <h3 className="mt-5 text-xs font-semibold uppercase text-slate-500">Human review</h3>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-slate-600">
                {card.human_review_requirements.map((item) => <li key={item}>{item}</li>)}
              </ul>
              <h3 className="mt-5 text-xs font-semibold uppercase text-slate-500">Explainability</h3>
              <p className="mt-2 text-xs text-slate-600"><span className="font-medium">{card.explainability.method}.</span> {card.explainability.detail}</p>
            </GlassCard>
          </div>
        </>
      )}
    </div>
  )
}

function EmptyChart({ message }: { message: string }) {
  return (
    <div className="grid h-56 place-items-center rounded-xl border border-dashed border-[rgb(var(--line))] bg-slate-50/60 px-6 text-center text-sm text-slate-500 dark:bg-white/[.02]">
      {message}
    </div>
  )
}
