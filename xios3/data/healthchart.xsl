<?xml version="1.0" encoding="UTF-8"?>
<!-- Line chart of one asset's health history, drawn as inline SVG by the render component.
     Bound document: host://data/history/<id>.xml  (<history><point age="" health=""/>...</history>)
     Plot area: 400 x 160 px inside a 440 x 200 canvas; health 0-100 on y, age 0..last age on x. -->
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">
  <xsl:output method="html" omit-xml-declaration="yes"/>

  <xsl:template match="/history">
    <xsl:variable name="maxAge" select="point[last()]/@age"/>
    <div>
      <div style="font-weight:bold;font-size:12px;">Health index (0-100) over age (<xsl:value-of select="@unit"/>)</div>
      <svg width="100%" height="200" viewBox="0 0 440 200" preserveAspectRatio="xMinYMin meet" xmlns="http://www.w3.org/2000/svg">
        <rect x="30" y="10" width="400" height="160" fill="none" stroke="#999999" stroke-width="1"/>
        <line x1="30" y1="90"  x2="430" y2="90"  stroke="#cccccc" stroke-width="1"/>
        <line x1="30" y1="42"  x2="430" y2="42"  stroke="#e0b000" stroke-width="1" stroke-dasharray="4 3"/>
        <line x1="30" y1="122" x2="430" y2="122" stroke="#d04040" stroke-width="1" stroke-dasharray="4 3"/>
        <text x="2" y="14"  font-size="10" fill="#666666">100</text>
        <text x="8" y="94"  font-size="10" fill="#666666">50</text>
        <text x="14" y="174" font-size="10" fill="#666666">0</text>
        <text x="30" y="192" font-size="10" fill="#666666">0</text>
        <text x="400" y="192" font-size="10" fill="#666666"><xsl:value-of select="$maxAge"/></text>
        <polyline fill="none" stroke="#2060c0" stroke-width="2">
          <xsl:attribute name="points">
            <xsl:for-each select="point">
              <xsl:value-of select="30 + (@age div $maxAge) * 400"/>
              <xsl:text>,</xsl:text>
              <xsl:value-of select="170 - (@health * 1.6)"/>
              <xsl:text> </xsl:text>
            </xsl:for-each>
          </xsl:attribute>
        </polyline>
      </svg>
    </div>
  </xsl:template>
</xsl:stylesheet>
