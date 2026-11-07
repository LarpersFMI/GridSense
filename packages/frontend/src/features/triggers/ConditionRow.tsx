import { Button, FormGroup, Tag } from '@blueprintjs/core'
import { Controller, useWatch, type Control, type UseFormSetValue } from 'react-hook-form'
import { Dataset, Trigger } from '@gridsense/shared/domain'
import type { z } from 'zod'
import { Dropdown } from '@/components/Dropdown'
import { ConditionValueInput } from './ConditionValueInput'
import { formatOperator } from './format'

type TriggerInput = z.input<typeof Trigger.Schema>

/** Operators by the type of the column they compare. */
const OPERATORS: Record<'number' | 'text', Trigger.Condition.Operator[]> = {
    number: ['>=', '<=', '>', '<', '==', '!=', 'between', 'in'],
    text:   ['==', '!=', 'in'],
}

interface ConditionRowProps {
    index:        number
    control:      Control<TriggerInput, unknown, Trigger>
    setValue:     UseFormSetValue<TriggerInput>
    descriptions: Partial<Record<Dataset.Name, Dataset.Description>>
    error:        string | undefined
    onRemove:     () => void
}

/** One condition: a dataset's column, an operator its type takes, and the value. Columns come from the file. */
export function ConditionRow({ index, control, setValue, descriptions, error, onRemove }: ConditionRowProps) {
    const condition = useWatch({ control, name: `conditions.${index}` })
    const columns = comparableColumns(descriptions[condition.dataset])
    const column = columns.find(candidate => candidate.name === condition.column) ?? null

    let operators = OPERATORS.number

    if (column?.type === 'text')
        operators = OPERATORS.text

    function handleDatasetChange(dataset: Dataset.Triggerable) {
        setValue(`conditions.${index}`, {
            dataset,
            column:   '',
            operator: '>=',
            value:    0,
        })
    }

    function handleColumnChange(name: string) {
        const next = columns.find(candidate => candidate.name === name)

        setValue(`conditions.${index}.column`, name)

        if (next?.type === 'text') {
            setValue(`conditions.${index}.operator`, '==')
            setValue(`conditions.${index}.value`, '')
        }
        else {
            setValue(`conditions.${index}.operator`, '>=')
            setValue(`conditions.${index}.value`, 0)
        }
    }

    function handleOperatorChange(operator: Trigger.Condition.Operator) {
        setValue(`conditions.${index}.operator`, operator)
        setValue(`conditions.${index}.value`, defaultValue(operator, column?.type ?? null))
    }

    return (
        <FormGroup intent={error ? 'danger' : 'none'} helperText={error} className='mb-2'>
            <div className='flex flex-wrap items-start gap-2'>
                <div className='w-32 shrink-0'>
                    <Dropdown
                        value={condition.dataset}
                        options={Dataset.Triggerable.options.map(name => ({ value: name, label: name }))}
                        onChange={handleDatasetChange}
                        fill
                    />
                </div>
                <div className='w-64 shrink-0'>
                    <Dropdown
                        value={condition.column}
                        options={columns.map(candidate => ({
                            value: candidate.name,
                            label: candidate.name,
                            hint:  <ColumnHint column={candidate} />,
                        }))}
                        onChange={handleColumnChange}
                        placeholder='Column…'
                        fill
                    />
                </div>
                <div className='w-28 shrink-0'>
                    <Dropdown
                        value={condition.operator}
                        options={operators.map(operator => ({ value: operator, label: formatOperator(operator) }))}
                        onChange={handleOperatorChange}
                        fill
                    />
                </div>
                <div className='min-w-40 flex-1'>
                    <Controller
                        control={control}
                        name={`conditions.${index}.value`}
                        render={({ field }) => (
                            <ConditionValueInput
                                operator={condition.operator}
                                columnType={column?.type ?? null}
                                value={field.value}
                                onChange={field.onChange}
                            />
                        )}
                    />
                </div>
                <Button icon='cross' variant='minimal' onClick={onRemove} aria-label='Remove condition' />
            </div>
        </FormGroup>
    )
}

/** A column's type, and whether the Watchdog computes it. */
function ColumnHint({ column }: { column: Dataset.Description.Column }) {
    return (
        <span className='flex gap-1'>
            {column.computed && <Tag minimal intent='primary'>computed</Tag>}
            <Tag minimal>{column.type}</Tag>
        </span>
    )
}

/** The columns a condition can compare: numbers and text. */
function comparableColumns(description: Dataset.Description | undefined): Dataset.Description.Column[] {
    if (!description)
        return []

    return description.columns.filter(column => column.type === 'number' || column.type === 'text')
}

function defaultValue(operator: Trigger.Condition.Operator, columnType: Dataset.Description.ColumnType | null): Trigger.Condition.Value {
    if (operator === 'between')
        return [0, 1]

    if (operator === 'in')
        return []

    if (columnType === 'text')
        return ''

    return 0
}
