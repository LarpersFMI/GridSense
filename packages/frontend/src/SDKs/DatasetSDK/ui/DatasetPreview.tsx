import { Button, Menu, MenuItem, NonIdealState, Spinner } from '@blueprintjs/core'
import { Cell, Column, ColumnHeaderCell, Table2, TruncatedFormat } from '@blueprintjs/table'
import type { Dataset } from '@gridsense/shared/domain'
import { ErrorNotice } from '@/components/ErrorNotice'
import { formatLocal } from '@/utils/format'
import { DatasetSDK } from '../sdk'

// Column widths, by what the column holds.
const COLUMN_WIDTHS: Record<Dataset.Description.ColumnType, number> = {
    timestamp: 190,
    number:    140,
    text:      260,
    boolean:   120,
    other:     170,
}

// Under the column's name, as Foundry writes it.
const TYPE_LABELS: Record<Dataset.Description.ColumnType, string> = {
    timestamp: 'Timestamp',
    number:    'Number',
    text:      'String',
    boolean:   'Boolean',
    other:     'Other',
}

interface DatasetPreviewProps {
    name:      Dataset.Name
    orderBy:   string | null
    onOrderBy: (column: string) => void
}

/**
 * A dataset's latest rows, newest first, in Blueprint's table, with Foundry-style headers: the column's name, its
 * type under it, a menu. Timestamps in Romanian time; long text truncated, the full value on hover. Fills its parent,
 * which must have a height.
 */
export function DatasetPreview({ name, orderBy, onOrderBy }: DatasetPreviewProps) {
    const [, [previewRequest]] = DatasetSDK.useWith(
        () => null,
        query => [query.preview(name, orderBy)],
    )

    const preview = previewRequest.data

    if (previewRequest.isPending && !preview)
        return <Spinner className='m-6' />

    if (previewRequest.isError) {
        return (
            <div className='flex flex-col items-start gap-2 p-4'>
                <ErrorNotice title="Couldn't read the dataset" error={previewRequest.error} />
                <Button text='Try again' icon='refresh' onClick={() => void previewRequest.refetch()} />
            </div>
        )
    }

    if (!preview || preview.rows.length === 0)
        return <NonIdealState icon='th' title='No rows yet' description='The file has no rows to show.' />

    return (
        <Table2
            className='dataset-preview'
            numRows={preview.rows.length}
            columnWidths={preview.columns.map(column => COLUMN_WIDTHS[column.type])}
            cellRendererDependencies={[preview]}
            enableGhostCells
        >
            {preview.columns.map(column => (
                <Column
                    key={column.name}
                    name={column.name}
                    columnHeaderCellRenderer={() => renderHeader(column, column.name === preview.orderBy, onOrderBy)}
                    cellRenderer={rowIndex => renderCell(column, preview.rows[rowIndex][column.name] ?? null)}
                />
            ))}
        </Table2>
    )
}

/**
 * The table clones what this returns to place it (its `style`), so it must be the ColumnHeaderCell itself — wrapped in
 * a component of ours, the style is lost and the headers drift from their columns. The ▾ is the table's own header
 * menu (`menuRenderer`): a button of ours inside the name would sit under the table's selection layer, unclickable.
 */
function renderHeader(column: Dataset.Description.Column, isOrderedBy: boolean, onOrderBy: (column: string) => void) {
    return (
        <ColumnHeaderCell
            name={column.name}
            menuIcon={isOrderedBy ? 'sort-desc' : 'caret-down'}
            menuRenderer={() => (
                <Menu>
                    <MenuItem
                        icon='sort-desc'
                        text='Newest first by this column'
                        disabled={column.type !== 'timestamp' || isOrderedBy}
                        onClick={() => onOrderBy(column.name)}
                    />
                    <MenuItem
                        icon='duplicate'
                        text='Copy column name'
                        onClick={() => void navigator.clipboard.writeText(column.name)}
                    />
                </Menu>
            )}
            nameRenderer={name => (
                <div className='flex min-w-0 flex-col overflow-hidden'>
                    <span className='truncate'>{name}</span>
                    <span className='text-xs text-gray-500'>{TYPE_LABELS[column.type]}</span>
                </div>
            )}
        />
    )
}

function renderCell(column: Dataset.Description.Column, value: Dataset.Preview.Cell) {
    if (value === null)
        return <Cell className='font-mono italic text-gray-400'>null</Cell>

    if (column.type === 'timestamp' && typeof value === 'string')
        return <Cell className='font-mono' tooltip={value}>{formatLocal(new Date(value))}</Cell>

    if (column.type === 'number')
        return <Cell className='text-right font-mono'>{String(value)}</Cell>

    return (
        <Cell className='font-mono'>
            <TruncatedFormat detectTruncation>{String(value)}</TruncatedFormat>
        </Cell>
    )
}
