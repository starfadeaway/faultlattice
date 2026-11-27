import { useEffect, useState } from "react"
import { VerticalAlignTopOutlined } from "@ant-design/icons"
import { Tooltip } from "antd"

export function BackToTop() {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const update = () => {
      const longPage = document.documentElement.scrollHeight > window.innerHeight + 160
      setVisible(longPage && window.scrollY > 320)
    }
    update()
    window.addEventListener("scroll", update, { passive: true })
    window.addEventListener("resize", update)
    return () => {
      window.removeEventListener("scroll", update)
      window.removeEventListener("resize", update)
    }
  }, [])

  function scrollToTop() {
    const reducedMotion = document.documentElement.dataset.motion === "off"
    window.scrollTo({ top: 0, behavior: reducedMotion ? "auto" : "smooth" })
  }

  return (
    <Tooltip title="回到顶端" placement="left">
      <button
        type="button"
        className={visible ? "back-to-top is-visible" : "back-to-top"}
        aria-label="回到顶端"
        aria-hidden={!visible}
        tabIndex={visible ? 0 : -1}
        onClick={scrollToTop}
      >
        <VerticalAlignTopOutlined />
      </button>
    </Tooltip>
  )
}
