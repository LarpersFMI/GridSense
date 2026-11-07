import { Tab, Tabs, type IconName, type TabId } from '@blueprintjs/core'

export interface ChoiceOption<T extends string> {
    value: T
    label: string
    icon?: IconName
}

interface ChoiceProps<T extends string> {
    id:       string
    value:    T
    options:  ChoiceOption<T>[]
    onChange: (value: T) => void
}

/** A choice between two or three options, as Blueprint's Tabs: all of them in view, the chosen one underlined. */
export function Choice<T extends string>({ id, value, options, onChange }: ChoiceProps<T>) {
    function handleChange(next: TabId) {
        const option = options.find(candidate => candidate.value === next)

        if (option)
            onChange(option.value)
    }

    return (
        <Tabs id={id} selectedTabId={value} onChange={handleChange}>
            {options.map(option => (
                <Tab key={option.value} id={option.value} icon={option.icon} title={option.label} />
            ))}
        </Tabs>
    )
}
