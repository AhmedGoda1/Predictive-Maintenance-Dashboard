<?xml version="1.0" encoding="UTF-8"?>
<!-- Skin for <screen>: nothing to see; the component only measures the window. -->
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">
  <xsl:template match="screen">
    <div id="{@name}" class="xios-screen" style="display:none" aria-hidden="true"></div>
  </xsl:template>
</xsl:stylesheet>
