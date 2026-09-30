import { formatBytes, formatPercent } from '../../utils/format'
import { statusColors } from '../../utils/statusColor'
import { severityFor } from '../../utils/alerts'
import './DiskUsageList.css'

export function DiskUsageList({ disks, alerts }) {
  if (!disks || disks.length === 0) {
    return <p className="disk-list-empty">No mounted partitions reported.</p>
  }

  return (
    <ul className="disk-list">
      {disks.map((disk) => {
        const status = severityFor(alerts, 'disk', disk.mountpoint)
        const { fg } = statusColors(status)
        return (
          <li className="disk-row" key={disk.mountpoint}>
            <div className="disk-row-label">
              <span className="disk-row-mount">{disk.mountpoint}</span>
              <span className="disk-row-device">{disk.device}</span>
            </div>
            <div className="disk-row-bar-track">
              <div
                className="disk-row-bar-fill"
                style={{ width: `${Math.min(disk.percent, 100)}%`, background: fg }}
              />
            </div>
            <span className="disk-row-percent num" style={{ color: fg }}>
              {formatPercent(disk.percent, { decimals: 0 })}
            </span>
            <span className="disk-row-bytes num">
              {formatBytes(disk.used_bytes)} / {formatBytes(disk.total_bytes)}
            </span>
          </li>
        )
      })}
    </ul>
  )
}
