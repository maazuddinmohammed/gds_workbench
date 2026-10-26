import { Link } from "@tanstack/react-router";

/**
 * One definition row listing the Subject Areas an Entity belongs to. The backend derives
 * them from the Entity's active Object sources, so they are read-only here.
 */
export function EntitySubjectAreas({ tenantId, projectId, areas }: {
  tenantId: number;
  projectId: number;
  areas: { subject_area_id: number; subject_area_name: string }[];
}) {
  return <div>
    <dt>Subject Areas</dt>
    <dd>{areas.length === 0 ? "None" : <ul className="entity-subject-areas" aria-label="Entity Subject Areas">
      {areas.map((area) => <li key={area.subject_area_id}>
        <Link className="text-action" to="/tenants/$tenantId/projects/$projectId/subject-areas/$subjectAreaId"
          params={{ tenantId: String(tenantId), projectId: String(projectId), subjectAreaId: String(area.subject_area_id) }}>
          {area.subject_area_name}
        </Link>
      </li>)}
    </ul>}</dd>
  </div>;
}
