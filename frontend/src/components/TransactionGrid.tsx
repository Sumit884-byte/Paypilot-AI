import { useEffect, useMemo } from 'react'
import { AgGridReact } from '@ag-grid-community/react'
import { ClientSideRowModelModule } from '@ag-grid-community/client-side-row-model'
import type { ColDef } from '@ag-grid-community/core'
import '@ag-grid-community/styles/ag-grid.css'
import '@ag-grid-community/styles/ag-theme-quartz.css'
import { money } from '../lib/api'

export type TransactionRow = {
  txn_id: string
  date: string
  type: string
  amount_inr: number
  category: string
  status: string
}

const gridModules = [ClientSideRowModelModule]

// Custom cell renderer for amount
function AmountCellRenderer({ value }: { value: any }) {
  return <span className="font-semibold text-navy-950 dark:text-white">{money(Number(value) || 0)}</span>
}

// Custom cell renderer for transaction type
function TypeCellRenderer({ value }: { value: any }) {
  const colors: Record<string, string> = {
    sale: 'text-emerald-600 dark:text-emerald-400',
    refund: 'text-rose-600 dark:text-rose-400',
    dispute: 'text-amber-600 dark:text-amber-400',
    expense: 'text-slate-600 dark:text-slate-400',
  }
  const icon: Record<string, string> = {
    sale: '$',
    refund: '↩',
    dispute: '⚠',
    expense: '–',
  }
  return (
    <span className={`inline-flex items-center gap-1.5 ${colors[value] || colors.sale}`}>
      <span className="text-xs">{icon[value] || '•'}</span>
      <span className="capitalize">{String(value)}</span>
    </span>
  )
}

// Custom cell renderer for status
function StatusCellRenderer({ value }: { value: any }) {
  const isCompleted = String(value).toLowerCase() === 'completed' || String(value).toLowerCase() === 's'
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider ${
        isCompleted
          ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
          : 'bg-amber-500/10 text-amber-700 dark:text-amber-300'
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${isCompleted ? 'bg-emerald-500' : 'bg-amber-500'}`} />
      {String(value)}
    </span>
  )
}

// AG Grid column definitions with PayScore theming
const columnDefs: ColDef<TransactionRow>[] = [
  {
    headerName: 'Date',
    field: 'date',
    width: 120,
    // Rows keep the ISO date so the column sorts chronologically
    valueFormatter: ({ value }) => new Date(value).toLocaleDateString('en-IN', { month: 'short', day: 'numeric', year: '2-digit' }),
    cellClass: 'text-slate-600 dark:text-slate-300 text-sm',
    headerClass: 'bg-paypal/5 text-paypal font-semibold text-xs uppercase tracking-wider',
  },
  {
    headerName: 'Type',
    field: 'type',
    width: 110,
    cellRenderer: TypeCellRenderer,
    headerClass: 'bg-paypal/5 text-paypal font-semibold text-xs uppercase tracking-wider',
  },
  {
    headerName: 'Amount',
    field: 'amount_inr',
    width: 130,
    cellRenderer: AmountCellRenderer,
    headerClass: 'bg-paypal/5 text-paypal font-semibold text-xs uppercase tracking-wider',
  },
  {
    headerName: 'Category',
    field: 'category',
    width: 140,
    cellClass: 'text-slate-600 dark:text-slate-300 text-sm capitalize',
    headerClass: 'bg-paypal/5 text-paypal font-semibold text-xs uppercase tracking-wider',
  },
  {
    headerName: 'Status',
    field: 'status',
    width: 120,
    cellRenderer: StatusCellRenderer,
    headerClass: 'bg-paypal/5 text-paypal font-semibold text-xs uppercase tracking-wider',
  },
]

const defaultColDef: ColDef<TransactionRow> = {
  flex: 1,
  minWidth: 110,
  resizable: true,
  sortable: true,
  filter: true,
}

export default function TransactionGrid({ rows }: { rows: TransactionRow[] }) {
  const rowStyle = useMemo(() => ({
    backgroundColor: 'transparent',
    fontFamily: 'Plus Jakarta Sans, Inter, system-ui, sans-serif',
  }), [])

  // AG Grid theme - enhanced Paypilot theme matching design system
  useEffect(() => {
    // Inject theme CSS dynamically for better integration
    const styleId = 'paypilot-ag-grid-theme'
    if (!document.getElementById(styleId)) {
      const style = document.createElement('style')
      style.id = styleId
      style.textContent = `
        .paypilot-grid .ag-root-wrapper {
          border-radius: 16px !important;
          border: 1px solid rgb(0 112 186 / 0.16) !important;
          background: rgb(var(--surface) / 0.5) !important;
          backdrop-filter: blur(20px);
          -webkit-backdrop-filter: blur(20px);
        }
        .paypilot-grid .ag-header {
          background: rgb(0 112 186 / 0.06) !important;
          border-bottom: 1px solid rgb(0 112 186 / 0.16) !important;
        }
        .paypilot-grid .ag-header-cell {
          color: #0070ba !important;
          font-weight: 700 !important;
          font-size: 10px !important;
          letter-spacing: 0.08em !important;
          text-transform: uppercase !important;
        }
        .paypilot-grid .ag-row:hover {
          background: rgb(0 112 186 / 0.05) !important;
        }
        .paypilot-grid .ag-row-odd {
          background: rgb(0 112 186 / 0.02) !important;
        }
        .paypilot-grid .ag-cell {
          border-right: 1px solid rgb(148 163 184 / 0.08) !important;
        }
        .paypilot-grid .ag-cell:last-child {
          border-right: none !important;
        }
        .paypilot-grid .ag-paging-panel {
          border-top: 1px solid rgb(0 112 186 / 0.12) !important;
        }
        .dark .paypilot-grid .ag-root-wrapper {
          border-color: rgb(255 255 255 / 0.1) !important;
          background: rgb(17 26 46 / 0.6) !important;
        }
        .dark .paypilot-grid .ag-header {
          background: rgb(0 112 186 / 0.1) !important;
          border-bottom-color: rgb(255 255 255 / 0.1) !important;
        }
        .dark .paypilot-grid .ag-header-cell {
          color: #009cde !important;
        }
        .dark .paypilot-grid .ag-row:hover {
          background: rgb(0 112 186 / 0.08) !important;
        }
        .dark .paypilot-grid .ag-row-odd {
          background: rgb(0 112 186 / 0.04) !important;
        }
        .dark .paypilot-grid .ag-cell {
          border-right-color: rgb(255 255 255 / 0.05) !important;
        }
        .dark .paypilot-grid .ag-paging-panel {
          border-top-color: rgb(255 255 255 / 0.1) !important;
        }
        .paypilot-grid .ag-row-animation {
          transition: background-color 0.2s ease;
        }
      `
      document.head.appendChild(style)
    }
    return () => {
      const style = document.getElementById(styleId)
      if (style) style.remove()
    }
  }, [])

  return (
    <div className="ag-theme-quartz paypilot-grid" style={{ height: 400 }}>
      <AgGridReact
        modules={gridModules}
        columnDefs={columnDefs}
        rowData={rows}
        rowHeight={52}
        getRowId={({ data }) => data.txn_id}
        defaultColDef={defaultColDef}
        rowStyle={rowStyle}
      />
    </div>
  )
}
