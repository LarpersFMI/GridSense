import { useEffect, useState } from 'react'
import { Button, InputGroup } from '@blueprintjs/core'
import { Pipeline } from '@gridsense/shared/domain'

interface CronInputProps {
    value:        string
    defaultValue: string
    disabled:     boolean
    onChange:     (cron: string) => void
}

/** A cron pattern, saved on Enter or when it loses focus — if it has five fields. Esc puts back the saved one. */
export function CronInput({ value, defaultValue, disabled, onChange }: CronInputProps) {
    const [draft, setDraft] = useState(value)

    useEffect(() => {
        setDraft(value)
    }, [value])

    const isValid = Pipeline.Schedule.Cron.safeParse(draft.trim()).success

    function save() {
        const cron = draft.trim().replace(/\s+/g, ' ')

        if (isValid && cron !== value)
            onChange(cron)
    }

    function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
        if (event.key === 'Enter')
            save()

        if (event.key === 'Escape')
            setDraft(value)
    }

    return (
        // Blueprint's input width wins over a Tailwind class on it: sized through this div.
        <div className='w-44'>
            <InputGroup
                size='small'
                className='font-mono'
                value={draft}
                disabled={disabled}
                intent={isValid ? 'none' : 'danger'}
                onValueChange={setDraft}
                onBlur={save}
                onKeyDown={handleKeyDown}
                rightElement={value !== defaultValue && !disabled
                    ? <Button icon='reset' variant='minimal' size='small' title={`Back to ${defaultValue}`} onClick={() => onChange(defaultValue)} />
                    : undefined}
            />
        </div>
    )
}
