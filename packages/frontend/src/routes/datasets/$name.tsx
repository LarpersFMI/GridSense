import { createFileRoute, notFound } from '@tanstack/react-router'
import { Dataset } from '@gridsense/shared/domain'
import { DatasetPage } from '@/features/datasets/DatasetPage'

/** The dataset viewer: `/datasets/predictions`, `/datasets/prices`. */
export const Route = createFileRoute('/datasets/$name')({
    params: {
        parse: params => {
            const name = Dataset.Name.safeParse(params.name)

            if (!name.success)
                throw notFound()

            return { name: name.data }
        },
    },
    component: DatasetRoute,
})

function DatasetRoute() {
    const { name } = Route.useParams()

    return <DatasetPage key={name} name={name} />
}
