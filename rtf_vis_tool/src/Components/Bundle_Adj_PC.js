import React, {useEffect, useState} from "react";
import {Canvas} from "react-three-fiber";
import '../stylesheets/Bundle_Adj_PC.css';

//Loading Helper Components
import CoordinateGrid from './CoordinateGrid';
import OrbitControlsComponent from './OrbitControlsComponent';
import PointMesh from './PointMesh';

//Point Cloud Renderer Component
//Spawned once the 'SfMData' node is clicked
const Bundle_Adj_PC = (props) => {
    const [pointCloudRaw, setPointCloudRaw] = useState([]);
    const [pointCloudJSX, setPointCloudJSX] = useState([]);
    const [showCoordGrid, setShowCoordGrid] = useState(true);
    const [pointRadius, setPointRadius] = useState(0.15);
    const pointSizeArr = [pointRadius];         //point size simply defined by the radius, initialized as 0.15

    //render points3D.txt from COLMAP ba_output directory
    useEffect(() => {
        // fetch the specific file from the public directory
        fetch('results/ba_input/points3D.txt')
            .then(function(response){
                return response.text();
            })
            .then(function(data){
                const arrStringPoints = data.split('\n');
                var finalPointsJSX = [];
                
                //remove the first 3 commented lines of points3D.txt
                for (var i = 0; i < 3; i++) {
                    arrStringPoints.shift();
                }

                const arrNumPoints = arrStringPoints.map(point => point.split(" ").map(Number));
                setPointCloudRaw(arrNumPoints);

                //loop through array. convert strings to numbers. append to final point cloud
                for (var index = 0; index < arrNumPoints.length; index += 1) {
                    var pointArr = arrNumPoints[index];
                    
                    finalPointsJSX.push(
                        <PointMesh  
                            position={[pointArr[1], pointArr[2], pointArr[3]]}  
                            color={`rgb(${pointArr[4]}, ${pointArr[5]}, ${pointArr[6]})`} 
                            size={pointSizeArr}/>
                    );
                }
                setPointCloudJSX(finalPointsJSX);
            })
    }, []);

    //Function that updates the radius of all points within a point cloud
    //Called everytime the react slider input is interacted with
    const updatePointSizes = (radius) => {
        var finalPointsJSX = [];
        for (var i = 0; i < pointCloudRaw.length; i += 1) {
            var pointArr = pointCloudRaw[i];
            
            finalPointsJSX.push(
                <PointMesh  
                    position={[pointArr[1], pointArr[2], pointArr[3]]}  
                    color={`rgb(${pointArr[4]}, ${pointArr[5]}, ${pointArr[6]})`} 
                    size={[radius]}/>
            );
        }
        setPointCloudJSX(finalPointsJSX);
    }

    return (
        <div className="ba-container">
            <h2>Bundle Adjustment Point Cloud</h2>
            <Canvas colorManagement camera={{ fov: 20, position: [50, 50, 50], up: [0,0,1]}}>
                <ambientLight intensity={0.5}/>
                <pointLight position={[100, 100, 100]} intensity={1} castShadow />
                <pointLight position={[-100, -100, -100]} intensity={0.8}/>
                <directionalLight 
                    position={[0,20,0]} 
                    intensity={1.5} 
                    shadow-mapSize-width={1024}
                    shadow-mapSize-height={1024}
                    shadow-camera-far={50}
                />
        
                {pointCloudJSX}
                {showCoordGrid && <CoordinateGrid />}
                <OrbitControlsComponent />
            </Canvas>

            <button className="ba_go_back_btn" onClick={() => props.toggleDA_PC(false)}>Go Back</button>
            <button className="toggle_grid_btn" onClick={() => setShowCoordGrid(!showCoordGrid)}>Toggle Coordinate Grid</button>

            <div className="point_size_slider">
                <p>Adjust Point Radius:</p>
                <input
                    type="range"
                    min="0.05"
                    max="0.25"
                    value={pointRadius} 
                    onChange={(e) => {
                        setPointRadius(e.target.value);
                        updatePointSizes(e.target.value);
                    }}
                    step="0.05"/>
                
                <p style={{position: "absolute", left: "0px", bottom: "-25px", fontSize: "small"}}>Small</p>
                <p style={{position: "absolute", right: "0px", bottom: "-25px", fontSize: "small"}}>Large</p>
            </div>

        </div>
    )
}

export default Bundle_Adj_PC;