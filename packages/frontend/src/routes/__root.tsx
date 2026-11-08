import { useEffect } from 'react'
import { Alignment, Navbar, Tab, Tabs, Tag } from '@blueprintjs/core'
import { createRootRoute, Outlet, useLocation, useNavigate } from '@tanstack/react-router'
import { Logo } from '@/components/Logo'
import { DatasetSDK } from '@/SDKs/DatasetSDK/sdk'
import { ForecasterSDK } from '@/SDKs/ForecasterSDK/sdk'
import { PipelineSDK } from '@/SDKs/PipelineSDK/sdk'
import { ReplaySDK } from '@/SDKs/ReplaySDK/sdk'
import { AgentSDK } from '@/SDKs/AgentSDK/sdk'
import { ReplayCard } from '@/features/replay/ReplayCard'
import { RealtimeSDK } from '@/SDKs/RealtimeSDK/sdk'
import { TriggerSDK } from '@/SDKs/TriggerSDK/sdk'
import { WatchdogSDK } from '@/SDKs/WatchdogSDK/sdk'

/** The app's sections: each a tab in the navbar, at its route. */
const SECTIONS = [
    { to: '/pipelines', icon: 'data-lineage', label: 'Pipelines' },
    { to: '/datasets', icon: 'database', label: 'Datasets' },
    { to: '/triggers', icon: 'antenna', label: 'Triggers' },
    { to: '/agent', icon: 'predictive-analysis', label: 'Agent' },
    { to: '/activity', icon: 'pulse', label: 'Activity' },
] as const

type Section = (typeof SECTIONS)[number]['to']

export const Route = createRootRoute({
    component: Shell,
})

/** The navbar around every page, and the live feeds every page reads: runs, pipeline runs, checks, every trigger's hits, previews. */
function Shell() {
    const [triggers] = TriggerSDK.useWith(
        TriggerSDK.selectors.list,
        query => [query.triggers],
    )

    const triggerIds = triggers.map(trigger => trigger.id).join(',')

    useEffect(() => {
        return ForecasterSDK.actions.run.watch()
    }, [])

    useEffect(() => {
        return DatasetSDK.actions.dataset.watch()
    }, [])

    useEffect(() => {
        return PipelineSDK.actions.run.watch()
    }, [])

    useEffect(() => {
        return ReplaySDK.actions.replay.watch()
    }, [])

    useEffect(() => {
        const stopThreads = AgentSDK.actions.thread.watch()
        const stopSlots = AgentSDK.actions.slot.watch()

        return () => {
            stopThreads()
            stopSlots()
        }
    }, [])

    useEffect(() => {
        return WatchdogSDK.actions.live.watch(TriggerSDK.selectors.list(TriggerSDK.state).map(trigger => trigger.id))
    }, [triggerIds])

    return (
        <div className='flex h-full flex-col'>
            {/* Blueprint's navbar padding wins over Tailwind's: the square sits flush left through an inline style. */}
            <Navbar style={{ paddingLeft: 0 }}>
                <Navbar.Group align={Alignment.START}>
                    <div className='mr-3 flex h-[50px] w-[50px] items-center justify-center bg-blue-600'>
                        <Logo />
                    </div>
                    <Navbar.Heading className='font-semibold'>GridSense</Navbar.Heading>
                    <Navbar.Divider />
                    <SectionTabs />
                </Navbar.Group>
                <Navbar.Group align={Alignment.END}>
                    <ConnectionTag />
                </Navbar.Group>
            </Navbar>
            {/* Room at the bottom for the floating replay card, so it never covers the end of a page. */}
            <main className='min-h-0 flex-1 overflow-auto pb-20'>
                <Outlet />
            </main>
            <ReplayCard />
        </div>
    )
}

/** Blueprint's Tabs as the app's navigation: the tab is the section the URL is in; choosing one goes to its route. */
function SectionTabs() {
    const navigate = useNavigate()
    const pathname = useLocation({ select: location => location.pathname })

    let selected: Section | undefined

    for (const section of SECTIONS)
        if (pathname.startsWith(section.to))
            selected = section.to

    // Loaded here too: the count of threads waiting for the operator shows on the Agent tab from any page.
    const [waiting] = AgentSDK.useWith(state => AgentSDK.selectors.inbox(state).length, query => [query.threads])

    function handleChange(next: Section) {
        void navigate({ to: next })
    }

    return (
        <Tabs id='sections' selectedTabId={selected} onChange={handleChange} large>
            {SECTIONS.map(section => (
                <Tab
                    key={section.to}
                    id={section.to}
                    icon={section.icon}
                    title={section.to === '/agent' && waiting > 0 ? <>{section.label}<NotificationDot count={waiting} /></> : section.label}
                />
            ))}
        </Tabs>
    )
}

/** A small notification bubble, raised beside a tab's label: how many things wait there. */
function NotificationDot({ count }: { count: number }) {
    return (
        <span className='relative -top-2 ml-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-semibold leading-none text-white'>
            {count}
        </span>
    )
}

function ConnectionTag() {
    const isConnected = RealtimeSDK.useStore(state => state.isConnected)

    if (isConnected)
        return <Tag intent='success' minimal icon='feed'>Live</Tag>

    return <Tag intent='warning' minimal icon='offline'>Reconnecting</Tag>
}
