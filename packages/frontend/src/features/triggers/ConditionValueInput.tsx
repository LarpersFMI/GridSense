import type { KeyboardEvent, ReactNode } from 'react'
import { InputGroup, NumericInput, TagInput } from '@blueprintjs/core'
import type { Dataset, Trigger } from '@gridsense/shared/domain'

interface ConditionValueInputProps {
    operator:   Trigger.Condition.Operator
    columnType: Dataset.Description.ColumnType | null       // null: the column isn't in the file (yet)
    value:      Trigger.Condition.Value
    onChange:   (value: Trigger.Condition.Value) => void
}

/** The value a condition compares with, shaped by its operator: one number or text, [low, high], or a list. */
export function ConditionValueInput({ operator, columnType, value, onChange }: ConditionValueInputProps) {
    if (operator === 'between') {
        let pair: [number, number] = [0, 0]

        if (Array.isArray(value) && value.length === 2)
            pair = [Number(value[0]), Number(value[1])]

        return (
            <div className='flex items-center gap-2'>
                <div className='w-28'>
                    <NumericInput
                        value={pair[0]}
                        onValueChange={low => onChange([low, pair[1]])}
                        buttonPosition='none'
                        fill
                    />
                </div>
                <span className='text-gray-500'>and</span>
                <div className='w-28'>
                    <NumericInput
                        value={pair[1]}
                        onValueChange={high => onChange([pair[0], high])}
                        buttonPosition='none'
                        fill
                    />
                </div>
            </div>
        )
    }

    if (operator === 'in') {
        let values: string[] = []

        if (Array.isArray(value))
            values = value.map(String)

        function handleValuesChange(next: ReactNode[]) {
            const texts = next.map(String)

            if (columnType === 'number')
                onChange(texts.map(Number).filter(number => !Number.isNaN(number)))
            else
                onChange(texts)
        }

        return (
            <TagInput
                values={values}
                onChange={handleValuesChange}
                placeholder='Type a value, then Enter'
                inputProps={{ onKeyDown: keepEnterInTags }}
                fill
            />
        )
    }

    if (columnType === 'number') {
        let number = 0

        if (typeof value === 'number')
            number = value

        return (
            <NumericInput
                value={number}
                onValueChange={onChange}
                minorStepSize={0.01}
                stepSize={0.05}
                fill
            />
        )
    }

    return (
        <InputGroup
            value={typeof value === 'string' ? value : String(value)}
            onValueChange={onChange}
            placeholder='ok'
            fill
        />
    )
}

/** Enter adds a tag; it mustn't also submit the trigger's form. */
function keepEnterInTags(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter')
        event.preventDefault()
}
