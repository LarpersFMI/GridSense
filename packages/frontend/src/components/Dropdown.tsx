import { useState, type ReactNode } from 'react'
import { Button, InputGroup, Menu, MenuItem, PopoverNext } from '@blueprintjs/core'

// Past this many options, the menu gets a filter box.
const FILTER_AFTER = 8

// The menu scales in from its button (PopoverNext's `scale` animation); shorter than Blueprint's 300 ms default.
const POPOVER_TRANSITION_MS = 200

export interface DropdownOption<T extends string> {
    value:  T
    label:  string
    hint?:  ReactNode            // shown on the right of the option: a type, "computed"
}

interface DropdownProps<T extends string> {
    value:        T | ''
    options:      DropdownOption<T>[]
    onChange:     (value: T) => void
    placeholder?: string
    fill?:        boolean
    className?:   string
}

/**
 * A select as a Blueprint popover menu, not the browser's native one. Long lists get a filter. PopoverNext
 * (floating-ui): Blueprint's older Popover places its content wrong under React 19.
 */
export function Dropdown<T extends string>({ value, options, onChange, placeholder, fill, className }: DropdownProps<T>) {
    const [isOpen, setIsOpen] = useState(false)
    const [filter, setFilter] = useState('')

    const selected = options.find(option => option.value === value) ?? null
    const query = filter.trim().toLowerCase()
    const shown = options.filter(option => query === '' || option.label.toLowerCase().includes(query))

    function handleSelect(option: DropdownOption<T>) {
        onChange(option.value)
        setIsOpen(false)
        setFilter('')
    }

    function handleInteraction(nextOpen: boolean) {
        setIsOpen(nextOpen)

        if (!nextOpen)
            setFilter('')
    }

    const menu = (
        <Menu className='max-h-80 overflow-auto'>
            {options.length > FILTER_AFTER && (
                <InputGroup
                    leftIcon='search'
                    placeholder='Filter…'
                    value={filter}
                    onValueChange={setFilter}
                    autoFocus
                    small
                    className='mb-1'
                />
            )}
            {shown.map(option => (
                <MenuItem
                    key={option.value}
                    text={option.label}
                    labelElement={option.hint}
                    roleStructure='listoption'
                    selected={option.value === value}
                    onClick={() => handleSelect(option)}
                />
            ))}
            {shown.length === 0 && <MenuItem disabled text='No match' />}
        </Menu>
    )

    return (
        <PopoverNext
            content={menu}
            isOpen={isOpen}
            onInteraction={handleInteraction}
            placement='bottom-start'
            animation='scale'
            transitionDuration={POPOVER_TRANSITION_MS}
            matchTargetWidth={fill}
            fill={fill}
            className={className}
        >
            <Button
                text={selected?.label ?? placeholder ?? 'Choose…'}
                endIcon='caret-down'
                alignText='start'
                fill={fill}
                className={selected === null ? 'text-gray-500' : undefined}
            />
        </PopoverNext>
    )
}
